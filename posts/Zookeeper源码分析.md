Zookeeper源码分析
2024-08-22
Zookeeper 是一个分布式协调服务。它主要用于维护配置信息、命名服务、分布式同步等。具有高可靠性和高性能，通过选举机制保证服务的可用性。能有效协调分布式系统中各个节点，确保系统稳定高效运行，是分布式架构中的重要组件。
01.jpg
源码解读
huizhang43

#### **1、zk的启动**



![img](http://pcc.huitogo.club/ec2d54ec357814640817a5414b1964ba)



重点看一下ZookeeperServerMain的main方法，主要包含三大块



```
AdminServer.start()   

	DummyAdminServer：什么都不做
	JettyAdminServer： 内嵌Servlet容器，用于访问ZookeeperServer支持的接口（命令行）

ServerCnxnFactory.startup(ZookeeperServer) 初始化 和 客户端之间的连接处理，分 加密模式 和 非加密模式

	NettyServerCnxnFactory：和客户端之间使用Netty传输
	NIOServerCnxnFactory：使用Http的NIO模式进行传输
	
		 start工作线程：
		 
				1 accept thread：接收新的连接 并委派给Selector Thread
				1-N selector threads: 实际select 请求的线程，哪个channel有流传输则进行select，支持多线程用于大量客户端发起请求的场景，避免selector thread变成性能瓶颈
				0-M socket I/O worker threads：实际工作线程，执行RequestProcessor，如果配置为0的话则直接在selector thread中执行
				1 connection expiration thread：根据会话时间（心跳）关闭空闲的客户端连接
				
		装配Zookeeper 服务端配置信息
				startdata()：加载磁盘数据（dataTree）到内存中，并获取最后一次有效的 zxid（节点序列号）
				startup()
						startSessionTracker()： 启动session会话跟踪管理器，leader 和 standalone模式下的 共用一个，其他的follow 服务 则关联到 leader上
						setupRequestProcessors()：配置请求链式处理器  PrepRequestProcessor -> SyncRequestProcessor -> FinalRequestProcessor
						registerJMX()：注册了一个 Zk的服务信息 和 数据信息

ContainerManager.start()：管理 和 清理 zk的数据节点
		checkContainers()：清理无子节点 和 ttl到期的叶子节点
```



简单的总结就是Zookeeper本质上就是管理它的数据节点（DataTree）



详细看下各子部分的代码



NIOServerCnxnFactory.start() 初始化 和 客户端之间的连接处理

```
public void start() {
    stopped = false;
    // 真正执行客户端的请求
    if (workerPool == null) {
        workerPool = new WorkerService(
                "NIOWorker", numWorkerThreads, false);
    }
    // epoll 模型
    // 都是damon 线程
    // 处理 和 验证请求，更新客户端连接状态，主要是讲请求体 转交给 Worker去执行
    for (SelectorThread thread : selectorThreads) {
        if (thread.getState() == Thread.State.NEW) {
            thread.start();
        }
    }
    // ensure thread is started once and only once
    // acceptThread 将 连接请求 ClientSocketChannerl加入 acceptQueue中
    if (acceptThread.getState() == Thread.State.NEW) {
        acceptThread.start();
    }
    // 关闭 过期的（失活）的客户端连接
    if (expirerThread.getState() == Thread.State.NEW) {
        expirerThread.start();
    }
}
```



可以看出这是一块典型的NIO的epoll模式设计，一个Accept Thread拖着多个Selector Thread，然后Selector Thread将读取的客户端连接通道的流信息报文请求分发到WorkPool中 等待Worker执行，最后是一个Exipirer Thread负责 心跳检查



**Accept Thread**

```
private boolean doAccept() {
    boolean accepted = false;
    SocketChannel sc = null;
    try {
        sc = acceptSocket.accept();
        accepted = true;
        InetAddress ia = sc.socket().getInetAddress();
        int cnxncount = getClientCnxnCount(ia);

        if (maxClientCnxns > 0 && cnxncount >= maxClientCnxns) {
            throw new IOException("Too many connections from " + ia
                    + " - max is " + maxClientCnxns);
        }

        LOG.debug("Accepted socket connection from "
                + sc.socket().getRemoteSocketAddress());
        sc.configureBlocking(false);

        // Round-robin assign this connection to a selector thread
        if (!selectorIterator.hasNext()) {
            selectorIterator = selectorThreads.iterator();
        }
        SelectorThread selectorThread = selectorIterator.next();
        if (!selectorThread.addAcceptedConnection(sc)) {
            throw new IOException(
                    "Unable to add connection to selector queue"
                            + (stopped ? " (shutdown in progress)" : ""));
        }
        acceptErrorLogger.flush();
    } catch (IOException e) {
        // accept, maxClientCnxns, configureBlocking
        acceptErrorLogger.rateLimitLog(
                "Error accepting new connection: " + e.getMessage());
        fastCloseSock(sc);
    }
    return accepted;
}
```



**Selector Thread**

```
private void select() {
    try {
        selector.select();

        Set<SelectionKey> selected = selector.selectedKeys();
        ArrayList<SelectionKey> selectedList =
                new ArrayList<SelectionKey>(selected);
        Collections.shuffle(selectedList);
        Iterator<SelectionKey> selectedKeys = selectedList.iterator();
        while (!stopped && selectedKeys.hasNext()) {
            SelectionKey key = selectedKeys.next();
            selected.remove(key);

            if (!key.isValid()) {
                cleanupSelectionKey(key);
                continue;
            }
            if (key.isReadable() || key.isWritable()) {
                handleIO(key);
            } else {
                LOG.warn("Unexpected ops in select " + key.readyOps());
            }
        }
    } catch (IOException e) {
        LOG.warn("Ignoring IOException while selecting", e);
    }
}
```



Expire Thread

```
public void run() {
    try {
        while (!stopped) {
            long waitTime = cnxnExpiryQueue.getWaitTime();
            if (waitTime > 0) {
                Thread.sleep(waitTime);
                continue;
            }
            for (NIOServerCnxn conn : cnxnExpiryQueue.poll()) {
                conn.close();
            }
        }

    } catch (InterruptedException e) {
        LOG.info("ConnnectionExpirerThread interrupted");
    }
}
```



NIOServerCnxnFactory.startdata() 加载磁盘数据（dataTree）到内存中，并获取最后一次有效的 zxid（节点序列号）

```
/**
 *  Restore sessions and data
 */
public void loadData() throws IOException, InterruptedException {
    /*
     * When a new leader starts executing Leader#lead, it 
     * invokes this method. The database, however, has been
     * initialized before running leader election so that
     * the server could pick its zxid for its initial vote.
     * It does it by invoking QuorumPeer#getLastLoggedZxid.
     * Consequently, we don't need to initialize it once more
     * and avoid the penalty of loading it a second time. Not 
     * reloading it is particularly important for applications
     * that host a large database.
     * 
     * The following if block checks whether the database has
     * been initialized or not. Note that this method is
     * invoked by at least one other method: 
     * ZooKeeperServer#startdata.
     *  
     * See ZOOKEEPER-1642 for more detail.
     */
    if(zkDb.isInitialized()){
        setZxid(zkDb.getDataTreeLastProcessedZxid());
    }
    else {
        setZxid(zkDb.loadDataBase());
    }
    
    // Clean up dead sessions
    LinkedList<Long> deadSessions = new LinkedList<Long>();
    for (Long session : zkDb.getSessions()) {
        if (zkDb.getSessionWithTimeOuts().get(session) == null) {
            deadSessions.add(session);
        }
    }

    for (long session : deadSessions) {
        // XXX: Is lastProcessedZxid really the best thing to use?
        killSession(session, zkDb.getDataTreeLastProcessedZxid());
    }

    // Make a clean snapshot
    takeSnapshot();
}
```



总结下就是 如果内存有的话直接获取最近一次的zxid，没有则从磁盘（zkdb）中获取，可以是本地文件 也可以是数据库，硬盘存储是以log的形式存储的，映射到内存中的快照则是DataTree结构



NIOServerCnxnFactory.startup()

```
public synchronized void startup() {
    if (sessionTracker == null) {
        createSessionTracker();
    }
    // 启动session会话跟踪管理器，leader 和 standalone模式下的 共用一个，其他的follow 服务 则关联到 leader上
    // 处理主从之间的 会话，清除过期会话
    startSessionTracker();
    // 启动请求链式处理器  PrepRequestProcessor -> SyncRequestProcessor -> FinalRequestProcessor
    // 有点类似于Netty 的 Processor模式
    setupRequestProcessors();

    // 通常使用JMX来监控系统的运行状态或管理系统的某些方面，比如清空缓存、重新加载配置文件等
    // 注册了一个 ZooKeeperServerBean 和 DataTreeBean
    // ZooKeeperServerBean : zk的服务信息
    // DataTreeBean： zk的内存数据信息，DataTree，一个hashtable保存数据信息，用于存取，一个Tree 用于磁盘序列化（快照）
    registerJMX();

    setState(State.RUNNING);
    notifyAll();
}
```



setupRequestProcessors()

```
protected void setupRequestProcessors() {
    RequestProcessor finalProcessor = new FinalRequestProcessor(this);
    RequestProcessor syncProcessor = new SyncRequestProcessor(this,
            finalProcessor);
    ((SyncRequestProcessor)syncProcessor).start();
    firstProcessor = new PrepRequestProcessor(this, syncProcessor);
    ((PrepRequestProcessor)firstProcessor).start();
}
```



可以看出请求处理链的先后顺序是PrepRequestProcessor -> SyncRequestProcessor -> FinalRequestProcessor，跟Netty里面配置的SocketProcessor有点像，比如先读取字符流转码 -> 请求处理 -> 输出字符流编码



ContainerManager.start() 管理 和 清理 zk的数据节点

```
/**
 * Manually check the containers. Not normally used directly
 */
public void checkContainers()
        throws InterruptedException {
    long minIntervalMs = getMinIntervalMs();
    for (String containerPath : getCandidates()) {
        long startMs = Time.currentElapsedTime();

        ByteBuffer path = ByteBuffer.wrap(containerPath.getBytes());
        Request request = new Request(null, 0, 0,
                ZooDefs.OpCode.deleteContainer, path, null);
        try {
            LOG.info("Attempting to delete candidate container: {}",
                    containerPath);
            requestProcessor.processRequest(request);
        } catch (Exception e) {
            LOG.error("Could not delete container: {}",
                    containerPath, e);
        }

        long elapsedMs = Time.currentElapsedTime() - startMs;
        long waitMs = minIntervalMs - elapsedMs;
        if (waitMs > 0) {
            Thread.sleep(waitMs);
        }
    }
}
```



就是清理无效的 数据节点，这里主要看下哪些是无效的数据节点



getCandidates()

```
protected Collection<String> getCandidates() {
    Set<String> candidates = new HashSet<String>();
    for (String containerPath : zkDb.getDataTree().getContainers()) {
        DataNode node = zkDb.getDataTree().getNode(containerPath);
        /*
            cversion > 0: keep newly created containers from being deleted
            before any children have been added. If you were to create the
            container just before a container cleaning period the container
            would be immediately be deleted.
         */
        if ((node != null) && (node.stat.getCversion() > 0) &&
                (node.getChildren().size() == 0)) {
            candidates.add(containerPath);
        }
    }
    for (String ttlPath : zkDb.getDataTree().getTtls()) {
        DataNode node = zkDb.getDataTree().getNode(ttlPath);
        if (node != null) {
            Set<String> children = node.getChildren();
            if ((children == null) || (children.size() == 0)) {
                if ( EphemeralType.get(node.stat.getEphemeralOwner()) == EphemeralType.TTL ) {
                    long elapsed = getElapsed(node);
                    long ttl = EphemeralType.TTL.getValue(node.stat.getEphemeralOwner());
                    if ((ttl != 0) && (getElapsed(node) > ttl)) {
                        candidates.add(ttlPath);
                    }
                }
            }
        }
    }
    return candidates;
}
```



无效的叶子节点即 没有子节点的节点 或者 ttl到期的 叶子节点





#### **2、zkclient 和 zkserver 的请求机制**



这里重点看下 Worker的工作范围



```
/**
 * Schedule work to be done by the thread assigned to this id. Thread
 * assignment is a single mod operation on the number of threads.  If a
 * worker thread pool is not being used, work is done directly by
 * this thread.
 */
public void schedule(WorkRequest workRequest, long id) {
    if (stopped) {
        workRequest.cleanup();
        return;
    }

    ScheduledWorkRequest scheduledWorkRequest =
        new ScheduledWorkRequest(workRequest);

    // If we have a worker thread pool, use that; otherwise, do the work
    // directly.
    int size = workers.size();
    if (size > 0) {
        try {
            // make sure to map negative ids as well to [0, size-1]|
            // 随机挑选一个幸运工人，线程池的最大数 在0~size-1之间
            int workerNum = ((int) (id % size) + size) % size;
            ExecutorService worker = workers.get(workerNum);
            worker.execute(scheduledWorkRequest);
        } catch (RejectedExecutionException e) {
            LOG.warn("ExecutorService rejected execution", e);
            workRequest.cleanup();
        }
    } else {
        // When there is no worker thread pool, do the work directly
        // and wait for its completion
        scheduledWorkRequest.run();
    }
}

// 工人开始工作了
private class ScheduledWorkRequest implements Runnable {
    
    @Override
    public void run() {
        try {
            // Check if stopped while request was on queue
            if (stopped) {
                workRequest.cleanup();
                return;
            }
            workRequest.doWork();
        } catch (Exception e) {
            LOG.warn("Unexpected exception", e);
            workRequest.cleanup();
        }
    }
}
```



从 workRequest.doWork() 可追踪到 zkServer.processPacket(this, incomingBuffer)

```
ZookeeperServer.processPacket(ServerCnxn, ByteBuffer)  处理请求报文
public void processPacket(ServerCnxn cnxn, ByteBuffer incomingBuffer) throws IOException {
    // We have the request, now process and setup for next
    InputStream bais = new ByteBufferInputStream(incomingBuffer);
    BinaryInputArchive bia = BinaryInputArchive.getArchive(bais);
    RequestHeader h = new RequestHeader();
    h.deserialize(bia, "header");
    // Through the magic of byte buffers, txn will not be
    // pointing
    // to the start of the txn
    incomingBuffer = incomingBuffer.slice();
    // 授权认证请求
    if (h.getType() == OpCode.auth) {
       //... 不关心的内容
    } else {
        // ssl请求
        if (h.getType() == OpCode.sasl) {
            // ... 不关心的内容
        } // 正文处理
        else {
            Request si = new Request(cnxn, cnxn.getSessionId(), h.getXid(),
              h.getType(), incomingBuffer, cnxn.getAuthInfo());
            si.setOwner(ServerCnxn.me);
            // Always treat packet from the client as a possible
            // local request.
            setLocalSessionFlag(si);
            // 提交请求
            submitRequest(si);
        }
    }
    cnxn.incrOutstandingRequests(h);
}
```



submitRequest(Request）

```
public void submitRequest(Request si) {
    // zk 服务端正在启动，稍等片刻
    if (firstProcessor == null) {
        synchronized (this) {
            try {
                // Since all requests are passed to the request
                // processor it should wait for setting up the request
                // processor chain. The state will be updated to RUNNING
                // after the setup.
                while (state == State.INITIAL) {
                    wait(1000);
                }
            } catch (InterruptedException e) {
                LOG.warn("Unexpected interruption", e);
            }
            if (firstProcessor == null || state != State.RUNNING) {
                throw new RuntimeException("Not started");
            }
        }
    }
    try {
        // 客户端有请求来了，说明它是活的
        touch(si.cnxn);
        boolean validpacket = Request.isValid(si.type);
        if (validpacket) {
            firstProcessor.processRequest(si);
            if (si.cnxn != null) {
                // 请求数 + 1，因为zk服务端会作一个等待处理的最大请求数量的限制
                incInProcess();
            }
        } else {
            LOG.warn("Received packet at server of unknown type " + si.type);
            new UnimplementedRequestProcessor().processRequest(si);
        }
    } catch (MissingSessionException e) {
        if (LOG.isDebugEnabled()) {
            LOG.debug("Dropping request: " + e.getMessage());
        }
    } catch (RequestProcessorException e) {
        LOG.error("Unable to process request:" + e.getMessage(), e);
    }
}
```



可以看到有我们熟悉的 FirstProcessor，根据我们之前配置的Processor链来看，第一个应该是PrepRequestProcessor

```
LinkedBlockingQueue<Request> submittedRequests = new LinkedBlockingQueue<Request>();

public void processRequest(Request request) {
    submittedRequests.add(request);
}
```

往阻塞队列里面加了一个任务处理，这里用一个队列 缓冲任务，可以实现异步操作



真正的处理在PrepRequestProcessor 的 线程任务中

```
public void run() {
    try {
        while (true) {
            Request request = submittedRequests.take();
            long traceMask = ZooTrace.CLIENT_REQUEST_TRACE_MASK;
            if (request.type == OpCode.ping) {
                traceMask = ZooTrace.CLIENT_PING_TRACE_MASK;
            }
            // 日志追踪，看是客户端请求日志还是心跳包日志
            if (LOG.isTraceEnabled()) {
                ZooTrace.logRequest(LOG, traceMask, 'P', request, "");
            }
            if (Request.requestOfDeath == request) {
                break;
            }
            // 实际执行
            pRequest(request);
        }
}

/**
 * This method will be called inside the ProcessRequestThread, which is a
 * singleton, so there will be a single thread calling this code.
 *
 * @param request
 */
protected void pRequest(Request request) throws RequestProcessorException {
    // LOG.info("Prep>>> cxid = " + request.cxid + " type = " +
    // request.type + " id = 0x" + Long.toHexString(request.sessionId));
    request.setHdr(null);
    request.setTxn(null);

    try {
        switch (request.type) {
        case OpCode.createContainer:
        case OpCode.create:
        case OpCode.create2:
            CreateRequest create2Request = new CreateRequest();
            pRequest2Txn(request.type, zks.getNextZxid(), request, create2Request, true);
            break;
        case OpCode.createTTL:
            CreateTTLRequest createTtlRequest = new CreateTTLRequest();
            pRequest2Txn(request.type, zks.getNextZxid(), request, createTtlRequest, true);
            break;
        case OpCode.deleteContainer:
        case OpCode.delete:
            DeleteRequest deleteRequest = new DeleteRequest();
            pRequest2Txn(request.type, zks.getNextZxid(), request, deleteRequest, true);
            break;
        case OpCode.setData:
            SetDataRequest setDataRequest = new SetDataRequest();                
            pRequest2Txn(request.type, zks.getNextZxid(), request, setDataRequest, true);
            break;
}
```



这里我们以createNode指令为例看看流程怎么执行的

```
private void pRequest2TxnCreate(int type, Request request, Record record, boolean deserialize) throws IOException, KeeperException {
    if (deserialize) {
        ByteBufferInputStream.byteBuffer2Record(request.request, record);
    }

    int flags;
    String path;
    List<ACL> acl;
    byte[] data;
    long ttl;
    if (type == OpCode.createTTL) {
        CreateTTLRequest createTtlRequest = (CreateTTLRequest)record;
        flags = createTtlRequest.getFlags();
        path = createTtlRequest.getPath();
        acl = createTtlRequest.getAcl();
        data = createTtlRequest.getData();
        ttl = createTtlRequest.getTtl();
    } else {
        CreateRequest createRequest = (CreateRequest)record;
        flags = createRequest.getFlags();
        path = createRequest.getPath();
        acl = createRequest.getAcl();
        data = createRequest.getData();
        ttl = -1;
    }
    // 节点类型
    CreateMode createMode = CreateMode.fromFlag(flags);
    validateCreateRequest(path, createMode, request, ttl);
    String parentPath = validatePathForCreate(path, request.sessionId);

    List<ACL> listACL = fixupACL(path, request.authInfo, acl);
    // 我理解的 是修正操作（事务），状态介于准备修改 和 修改完成之间
    ChangeRecord parentRecord = getRecordForPath(parentPath);

    checkACL(zks, parentRecord.acl, ZooDefs.Perms.CREATE, request.authInfo);
    int parentCVersion = parentRecord.stat.getCversion();
    if (createMode.isSequential()) {
        path = path + String.format(Locale.ENGLISH, "%010d", parentCVersion);
    }
    validatePath(path, request.sessionId);
    try {
        // 节点有 修改操作，即不为空
        if (getRecordForPath(path) != null) {
            throw new KeeperException.NodeExistsException(path);
        }
    } catch (KeeperException.NoNodeException e) {
        // ignore this one
    }
    // 判断父节点是否叶子节点
    boolean ephemeralParent = EphemeralType.get(parentRecord.stat.getEphemeralOwner()) == EphemeralType.NORMAL;
    if (ephemeralParent) {
        throw new KeeperException.NoChildrenForEphemeralsException(path);
    }
    // 修改父节点的 版本号
    int newCversion = parentRecord.stat.getCversion() + 1;
    if (type == OpCode.createContainer) {
        request.setTxn(new CreateContainerTxn(path, data, listACL, newCversion));
    } else if (type == OpCode.createTTL) {
        request.setTxn(new CreateTTLTxn(path, data, listACL, newCversion, ttl));
    } else {
        request.setTxn(new CreateTxn(path, data, listACL, createMode.isEphemeral(),
                newCversion));
    }
    StatPersisted s = new StatPersisted();
    if (createMode.isEphemeral()) {
        s.setEphemeralOwner(request.sessionId);
    }
    //写时复制
    parentRecord = parentRecord.duplicate(request.getHdr().getZxid());
    parentRecord.childCount++;
    parentRecord.stat.setCversion(newCversion);
    addChangeRecord(parentRecord);
    addChangeRecord(new ChangeRecord(request.getHdr().getZxid(), path, s, 0, listACL));
}
```



这里在校验完 新增节点 和 新增节点的父节点有效性后 使用 写时复制 的方式 修改父节点的信息（版本号、子节点数量），添加了 新增节点的修改记录，addChangeRecord操作 向事件队列中 添加新增事件信息

```
private void addChangeRecord(ChangeRecord c) {
    synchronized (zks.outstandingChanges) {
        // 事件队列（双端）
        zks.outstandingChanges.add(c);
        // 修改事件内容（非安全的）
        zks.outstandingChangesForPath.put(c.path, c);
    }
}
```



按照我们之前整理的调用链的顺序，下一个是 SyncRequestProcessor，这个处理器是将节点事件生成snapshot 存入磁盘，我们后面再看



最后一个处理器是 FinalRequestProcessor，也就是真正对数据进行操作的地方，看一下 processRequest 方法

```
synchronized (zks.outstandingChanges) {
    // Need to process local session requests
    // 修改本地内存（DataTree）中的节点信息
    rc = zks.processTxn(request);

    // request.hdr is set for write requests, which are the only ones
    // that add to outstandingChanges.
    if (request.getHdr() != null) {
        TxnHeader hdr = request.getHdr();
        Record txn = request.getTxn();
        long zxid = hdr.getZxid();
        while (!zks.outstandingChanges.isEmpty()
               && zks.outstandingChanges.peek().zxid <= zxid) {
            // 移除事务id 小的       
            ChangeRecord cr = zks.outstandingChanges.remove();
            if (cr.zxid < zxid) {
                LOG.warn("Zxid outstanding " + cr.zxid
                         + " is less than current " + zxid);
            }
            // 重复操作同一 path 进行移除，已最新的操作为准
            if (zks.outstandingChangesForPath.get(cr.path) == cr) {
                zks.outstandingChangesForPath.remove(cr.path);
            }
        }
    }

    // do not add non quorum packets to the queue.
    // 新增日志记录（时间轴的形式），用于从节点之间的数据同步
    if (request.isQuorum()) {
        zks.getZKDatabase().addCommittedProposal(request);
    }
}
if (request.cnxn == null) {
    return;
}
ServerCnxn cnxn = request.cnxn;

String lastOp = "NA";
// zk客户端连接数减 1
zks.decInProcess();
Code err = Code.OK;
// 根据事件节点类型 返回 响应报文
Record rsp = null;
...
//审计操作
}
对事件缓冲队列进行弹出操作，先写入内存再写入磁盘，最后返回响应报文。
```





#### **3、zk的数据怎么持久化？**



先总结一下，数据 分别存在内存 和 磁盘中，通常 对节点的 CRUD发生在内存中（不难理解，快嘛），以DataTree（TreeNode）的数据结构进行存储； 持久化入磁盘的以l snapshot 文件的方式进行存储，可用于 初始化数据、数据恢复等后台耗时操作；还有一种内存数据用于主从节点的数据同步，基于 log 的数据结构；



对数据的操作都在ZkDatabase中

```
public class ZKDatabase {

    private static final Logger LOG = LoggerFactory.getLogger(ZKDatabase.class);

    /**
     * make sure on a clear you take care of all these members.
     */
    protected DataTree dataTree;
    protected ConcurrentHashMap<Long, Integer> sessionsWithTimeouts;
    //FileTxnSnapLog是管理日志文件和持久化文件的对象
    protected FileTxnSnapLog snapLog;
    protected long minCommittedLog, maxCommittedLog;

    /**
     * Default value is to use snapshot if txnlog size exceeds 1/3 the size of snapshot
     */
    public static final String SNAPSHOT_SIZE_FACTOR = "zookeeper.snapshotSizeFactor";
    public static final double DEFAULT_SNAPSHOT_SIZE_FACTOR = 0.33;
    private double snapshotSizeFactor;

    public static final int commitLogCount = 500;
    protected static int commitLogBuffer = 700;
    protected LinkedList<Proposal> committedLog = new LinkedList<Proposal>();
    protected ReentrantReadWriteLock logLock = new ReentrantReadWriteLock();
    volatile private boolean initialized = false;
    ...    
}
```



数据节点的类型有以下几种

```
/**
 * The znode will not be automatically deleted upon client's disconnect.
 */
PERSISTENT (0, false, false, false, false),
/**
* The znode will not be automatically deleted upon client's disconnect,
* and its name will be appended with a monotonically increasing number.
*/
PERSISTENT_SEQUENTIAL (2, false, true, false, false),
/**
 * The znode will be deleted upon the client's disconnect.
 */
EPHEMERAL (1, true, false, false, false),
/**
 * The znode will be deleted upon the client's disconnect, and its name
 * will be appended with a monotonically increasing number.
 */
EPHEMERAL_SEQUENTIAL (3, true, true, false, false),
/**
 * The znode will be a container node. Container
 * nodes are special purpose nodes useful for recipes such as leader, lock,
 * etc. When the last child of a container is deleted, the container becomes
 * a candidate to be deleted by the server at some point in the future.
 * Given this property, you should be prepared to get
 */
CONTAINER (4, false, false, true, false),
/**
 * The znode will not be automatically deleted upon client's disconnect.
 * However if the znode has not been modified within the given TTL, it
 * will be deleted once it has no children.
 */
PERSISTENT_WITH_TTL(5, false, false, false, true),
/**
 * The znode will not be automatically deleted upon client's disconnect,
 * and its name will be appended with a monotonically increasing number.
 * However if the znode has not been modified within the given TTL, it
 * will be deleted once it has no children.
 */
PERSISTENT_SEQUENTIAL_WITH_TTL(6, false, true, false, true);
```



还是以创建节点为例，先看一下内存中怎么 插入节点的，内存的核心操作类是DataTree，看一下DataTree.createNode()

```
/**
 * Add a new node to the DataTree.
 * @param path
 *             Path for the new node.
 * @param data
 *            Data to store in the node.
 * @param acl
 *            Node acls
 * @param ephemeralOwner
 *            the session id that owns this node. -1 indicates this is not
 *            an ephemeral node.
 * @param zxid
 *            Transaction ID
 * @param time
 * @param outputStat
 *             A Stat object to store Stat output results into.
 * @throws NodeExistsException
 * @throws NoNodeException
 * @throws KeeperException
 */
public void createNode(final String path, byte data[], List<ACL> acl,
        long ephemeralOwner, int parentCVersion, long zxid, long time, Stat outputStat)
        throws KeeperException.NoNodeException,
        KeeperException.NodeExistsException {
    int lastSlash = path.lastIndexOf('/');
    String parentName = path.substring(0, lastSlash);
    String childName = path.substring(lastSlash + 1);
    StatPersisted stat = new StatPersisted();
    stat.setCtime(time);
    stat.setMtime(time);
    stat.setCzxid(zxid);
    stat.setMzxid(zxid);
    stat.setPzxid(zxid);
    stat.setVersion(0);
    stat.setAversion(0);
    stat.setEphemeralOwner(ephemeralOwner);
    DataNode parent = nodes.get(parentName);
    if (parent == null) {
        throw new KeeperException.NoNodeException();
    }
    synchronized (parent) {
        Set<String> children = parent.getChildren();
        if (children.contains(childName)) {
            throw new KeeperException.NodeExistsException();
        }

        if (parentCVersion == -1) {
            parentCVersion = parent.stat.getCversion();
            parentCVersion++;
        }
        // 1. 修改父节点
        parent.stat.setCversion(parentCVersion);
        parent.stat.setPzxid(zxid);
        // 根据acl 转换成引用数量值
        // acl是节点的权限信息
        Long longval = aclCache.convertAcls(acl);
        DataNode child = new DataNode(data, longval, stat);
        parent.addChild(childName);
        // 2. 添加新增节点
        nodes.put(path, child);
        // 3. 将新增节点分类
        EphemeralType ephemeralType = EphemeralType.get(ephemeralOwner);
        if (ephemeralType == EphemeralType.CONTAINER) {
            containers.add(path);
        } else if (ephemeralType == EphemeralType.TTL) {
            ttls.add(path);
        } else if (ephemeralOwner != 0) {
            HashSet<String> list = ephemerals.get(ephemeralOwner);
            if (list == null) {
                list = new HashSet<String>();
                ephemerals.put(ephemeralOwner, list);
            }
            synchronized (list) {
                list.add(path);
            }
        }
        // 4. 复制出新增节点 状态信息 （用于返回）
        if (outputStat != null) {
           child.copyStat(outputStat);
        }
    }
    // now check if its one of the zookeeper node child
    // 5. 判断是否到系统节点下（比如手动添加引用信息）
    if (parentName.startsWith(quotaZookeeper)) {
        // now check if its the limit node
        if (Quotas.limitNode.equals(childName)) {
            // this is the limit node
            // get the parent and add it to the trie
            pTrie.addPath(parentName.substring(quotaZookeeper.length()));
        }
        if (Quotas.statNode.equals(childName)) {
            updateQuotaForPath(parentName
                    .substring(quotaZookeeper.length()));
        }
    }
    // also check to update the quotas for this node
    // 6. 修改节点的引用数
    String lastPrefix = getMaxPrefixWithQuota(path);
    if(lastPrefix != null) {
        // ok we have some match and need to update
        updateCount(lastPrefix, 1);
        updateBytes(lastPrefix, data == null ? 0 : data.length);
    }
    // 触发节点 watch事件
    dataWatches.triggerWatch(path, Event.EventType.NodeCreated);
    childWatches.triggerWatch(parentName.equals("") ? "/" : parentName,
            Event.EventType.NodeChildrenChanged);
}
```



看下第二种写入内存中的 log 格式，用于主从之间的数据同步

```
/**
 * maintains a list of last <i>committedLog</i>
 *  or so committed requests. This is used for
 * fast follower synchronization.
 * @param request committed request
 */
public void addCommittedProposal(Request request) {
    // 读写锁
    WriteLock wl = logLock.writeLock();
    try {
        wl.lock();
        // 现在最大提交日志记录大小默认为500
        if (committedLog.size() > commitLogCount) {
            committedLog.removeFirst();
            // 挤出一个后取最小的
            minCommittedLog = committedLog.getFirst().packet.getZxid();
        }
        if (committedLog.isEmpty()) {
            minCommittedLog = request.zxid;
            maxCommittedLog = request.zxid;
        }

        byte[] data = SerializeUtils.serializeRequest(request);
        // 定制日志包信息
        QuorumPacket pp = new QuorumPacket(Leader.PROPOSAL, request.zxid, data, null);
        Proposal p = new Proposal();
        p.packet = pp;
        p.request = request;
        // 新增一条提议 = 定制日志包 + request信息
        committedLog.add(p);
        // 修改最大提交日志偏移量
        maxCommittedLog = p.packet.getZxid();
    } finally {
        wl.unlock();
    }
}
```



committedLog 默认最多可以存储500条日志记录，超出时 则删除最老一条数据



在看磁盘操作时，我们先回过头看一下 请求数据处理的第二条处理链 SyncRequestProcessor.processRequest()

```
public void processRequest(Request request) {
    queuedRequests.add(request);
}
```



这里同样使用一条队列实现异步操作，实际执行代码在SyncRequestProcessor.run()中

```
public void run() {
    try {
        // 生成快照数量
        int logCount = 0;

        // we do this in an attempt to ensure that not all of the servers
        // in the ensemble take a snapshot at the same time
        int randRoll = r.nextInt(snapCount/2);
        while (true) {
            Request si = null;
            if (toFlush.isEmpty()) {
                si = queuedRequests.take();
            } else {
                si = queuedRequests.poll();
                if (si == null) {
                    flush(toFlush);
                    continue;
                }
            }
            if (si == requestOfDeath) {
                break;
            }
            if (si != null) {
                // track the number of records written to the log
                // 追加日志记录 .log.21212
                if (zks.getZKDatabase().append(si)) {
                    logCount++;
                    // 生成快照数量过多过快时，进行rollback
                    if (logCount > (snapCount / 2 + randRoll)) {
                        randRoll = r.nextInt(snapCount/2);
                        // roll the log
                        zks.getZKDatabase().rollLog();
                        // take a snapshot
                        // 生成快照的快照线程
                        if (snapInProcess != null && snapInProcess.isAlive()) {
                            LOG.warn("Too busy to snap, skipping");
                        } else {
                            snapInProcess = new ZooKeeperThread("Snapshot Thread") {
                                    public void run() {
                                        try {
                                            zks.takeSnapshot();
                                        } catch(Exception e) {
                                            LOG.warn("Unexpected exception", e);
                                        }
                                    }
                                };
                            snapInProcess.start();
                        }
                        logCount = 0;
                    }
                } else if (toFlush.isEmpty()) {
                    // optimization for read heavy workloads
                    // iff this is a read, and there are no pending
                    // flushes (writes), then just pass this to the next
                    // processor
                    if (nextProcessor != null) {
                        nextProcessor.processRequest(si);
                        if (nextProcessor instanceof Flushable) {
                            ((Flushable)nextProcessor).flush();
                        }
                    }
                    continue;
                }
                toFlush.add(si);
                // 追加记录达到1000条进行落盘（刷入磁盘）
                if (toFlush.size() > 1000) {
                    // 落盘 即 
                    flush(toFlush);
                }
            }
        }
    } catch (Throwable t) {
        handleException(this.getName(), t);
    } finally{
        running = false;
    }
    LOG.info("SyncRequestProcessor exited!");
}
```



实际存储磁盘有两种形式，一种是追加日志记录 .log ；一种是以快照 snapshot 的方式 存储，相关操作在 FileTxnSnapLog 中



追加日志记录 FileTxnSnapLog.append()

```
public synchronized boolean append(TxnHeader hdr, Record txn)
    throws IOException
{
    if (hdr == null) {
        return false;
    }
    if (hdr.getZxid() <= lastZxidSeen) {
        LOG.warn("Current zxid " + hdr.getZxid()
                + " is <= " + lastZxidSeen + " for "
                + hdr.getType());
    } else {
        lastZxidSeen = hdr.getZxid();
    }
    if (logStream==null) {
       if(LOG.isInfoEnabled()){
            LOG.info("Creating new log file: " + Util.makeLogName(hdr.getZxid()));
       }

       logFileWrite = new File(logDir, Util.makeLogName(hdr.getZxid()));
       fos = new FileOutputStream(logFileWrite);
       logStream=new BufferedOutputStream(fos);
       oa = BinaryOutputArchive.getArchive(logStream);
       FileHeader fhdr = new FileHeader(TXNLOG_MAGIC,VERSION, dbId);
       fhdr.serialize(oa, "fileheader");
       // Make sure that the magic number is written before padding.
       logStream.flush();
       filePadding.setCurrentSize(fos.getChannel().position());
       streamsToFlush.add(fos);
    }
    filePadding.padFile(fos.getChannel());
    byte[] buf = Util.marshallTxnEntry(hdr, txn);
    if (buf == null || buf.length == 0) {
        throw new IOException("Faulty serialization for header " +
                "and txn");
    }
    Checksum crc = makeChecksumAlgorithm();
    crc.update(buf, 0, buf.length);
    oa.writeLong(crc.getValue(), "txnEntryCRC");
    Util.writeTxnBytes(oa, buf);

    return true;
}
```



追加记录的 输出流会预先保存在streamsToFlush中，等待toFlush的队列数量达到1000条即可刷入磁盘，即FileTxnSnapLog.commit()

```
/**
 * commit the logs. make sure that everything hits the
 * disk
 */
public synchronized void commit() throws IOException {
    if (logStream != null) {
        logStream.flush();
    }
    for (FileOutputStream log : streamsToFlush) {
        log.flush();
        if (forceSync) {
            long startSyncNS = System.nanoTime();

            FileChannel channel = log.getChannel();
            channel.force(false);

            syncElapsedMS = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startSyncNS);
            if (syncElapsedMS > fsyncWarningThresholdMS) {
                if(serverStats != null) {
                    serverStats.incrementFsyncThresholdExceedCount();
                }
                LOG.warn("fsync-ing the write ahead log in "
                        + Thread.currentThread().getName()
                        + " took " + syncElapsedMS
                        + "ms which will adversely effect operation latency. "
                        + "File size is " + channel.size() + " bytes. "
                        + "See the ZooKeeper troubleshooting guide");
            }
        }
    }
    while (streamsToFlush.size() > 1) {
        streamsToFlush.removeFirst().close();
    }
}
```



再看一下快照文件的生成方式，快照是由snapInProcess线程异步执行的，有新增追加记录的时候进行触发，生成快照的代码如下

```
public void takeSnapshot(){
    try {
        txnLogFactory.save(zkDb.getDataTree(), zkDb.getSessionWithTimeOuts());
    } catch (IOException e) {
        LOG.error("Severe unrecoverable error, exiting", e);
        // This is a severe error that we cannot recover from,
        // so we need to exit
        System.exit(10);
    }
}

/**
 * save the datatree and the sessions into a snapshot
 * @param dataTree the datatree to be serialized onto disk
 * @param sessionsWithTimeouts the session timeouts to be
 * serialized onto disk
 * @throws IOException
 */
public void save(DataTree dataTree,
        ConcurrentHashMap<Long, Integer> sessionsWithTimeouts)
    throws IOException {
    long lastZxid = dataTree.lastProcessedZxid;
    File snapshotFile = new File(snapDir, Util.makeSnapshotName(lastZxid));
    LOG.info("Snapshotting: 0x{} to {}", Long.toHexString(lastZxid),
            snapshotFile);
    snapLog.serialize(dataTree, sessionsWithTimeouts, snapshotFile);
}
```



快照文件生成过快（不一定可以全部同步到子节点）时会触发一个rollback操作，也是调用FileTxnSnapLog.rollLog()

```
/**
 * rollover the current log file to a new one.
 * @throws IOException
 */
public synchronized void rollLog() throws IOException {
    if (logStream != null) {
        this.logStream.flush();
        this.logStream = null;
        oa = null;
    }
}
```



最后顺便看一下 磁盘里的log文件怎么恢复成 内存中的 DataTree结构，这里调用了FileTxnSnapLog.restore()方法

```
/**
 * this function restores the server
 * database after reading from the
 * snapshots and transaction logs
 * @param dt the datatree to be restored
 * @param sessions the sessions to be restored
 * @param listener the playback listener to run on the
 * database restoration
 * @return the highest zxid restored
 * @throws IOException
 */
public long restore(DataTree dt, Map<Long, Integer> sessions,
                    PlayBackListener listener) throws IOException {
    // 1. 选取100条快照文件，找出最有效最新的一条，将文件的后缀名（二进制）转十进制即最近的一次事务id
    long deserializeResult = snapLog.deserialize(dt, sessions);
    FileTxnLog txnLog = new FileTxnLog(dataDir);

    // 快速的 根据日志记录 文件（列表） 获取
    RestoreFinalizer finalizer = () -> {
        long highestZxid = fastForwardFromEdits(dt, sessions, listener);
        return highestZxid;
    };
    if (-1L == deserializeResult) {
        /* this means that we couldn't find any snapshot, so we need to
         * initialize an empty database (reported in ZOOKEEPER-2325) */
        // 2. 从日志追加记录里面获取最近的一次事务id
        if (txnLog.getLastLoggedZxid() != -1) {
            // ZOOKEEPER-3056: provides an escape hatch for users upgrading
            // from old versions of zookeeper (3.4.x, pre 3.5.3).
            if (!trustEmptySnapshot) {
                throw new IOException(EMPTY_SNAPSHOT_WARNING + "Something is broken!");
            } else {
                LOG.warn("{}This should only be allowed during upgrading.", EMPTY_SNAPSHOT_WARNING);
                return finalizer.run();
            }
        }
        // 3. 对DataTree 进行一次快照
        save(dt, (ConcurrentHashMap<Long, Integer>)sessions);
        /* return a zxid of zero, since we the database is empty */
        return 0;
    }

    return finalizer.run();
}
```





#### **4、zk怎么保证线程安全 和 数据的一致性**



##### 1）zxid 的原子性，每一个客户端请求会带上xid（事务id）已经服务端会生成全局zxid，执行请求的时候会校验zxid的时效性



客户端发起请求时，Zookeeper服务端会自动生成唯一的递增的zxid 作为事务id，生成途径如下：

```
protected void pRequest(Request request) throws RequestProcessorException 
    try {
        switch (request.type) {
            case OpCode.createContainer:
            case OpCode.create:
            case OpCode.create2:
                CreateRequest create2Request = new CreateRequest();
                pRequest2Txn(request.type, zks.getNextZxid(), request, create2Request, true);
                //... 不重要省略了
    }
}
private final AtomicLong hzxid = new AtomicLong(0);

long getNextZxid() {
    return hzxid.incrementAndGet();
}
```



这个zxid在很多场景都会用到，作为单次客户端发起事务的唯一标识，可作为日志追加记录的文件名（转二进制）；也可以作为zk执行时参考的依据，比如worker执行某个zxid的时候，从事件队列中弹出事件（ChangeRecord）时可以比较zxid的大小，如果小的话说明已经过时了，可以remove掉

```
while (!zks.outstandingChanges.isEmpty()
       && zks.outstandingChanges.peek().zxid <= zxid) {
    ChangeRecord cr = zks.outstandingChanges.remove();
    if (cr.zxid < zxid) {
        LOG.warn("Zxid outstanding " + cr.zxid
                 + " is less than current " + zxid);
    }
    if (zks.outstandingChangesForPath.get(cr.path) == cr) {
        zks.outstandingChangesForPath.remove(cr.path);
    }
}
```



另外存放 节点修改事件的 数据结构是 HashMap，可以保证针对某一个path 的修改操作只会存在最新的一条

```
// this data structure must be accessed under the outstandingChanges lock
final HashMap<String, ChangeRecord> outstandingChangesForPath =
    new HashMap<String, ChangeRecord>();
```



##### 2）修改 DataNode 的操作，写时复制



有修改事件需要修改父节点时 会 duplicate 一下父节点的最新操作（如果没有则从DataTree中新建一个），写时复制，避免直接修改原事件信息

```
// 获取最近一次针对父节点的操作 如果没有 则新建一个
ChangeRecord parentRecord = getRecordForPath(parentPath);
ChangeRecord nodeRecord = getRecordForPath(path);
// ... 不重要省略了
parentRecord = parentRecord.duplicate(request.getHdr().getZxid());
parentRecord.childCount--;
addChangeRecord(parentRecord);
addChangeRecord(new ChangeRecord(request.getHdr().getZxid(), path, null, -1, null));
```



##### 3）加锁



典型的例子是需要修改 outstandingChangesForPath 的数据时，都需要进行加锁

```
private ChangeRecord getRecordForPath(String path) throws KeeperException.NoNodeException {
    ChangeRecord lastChange = null;
    synchronized (zks.outstandingChanges) {
        lastChange = zks.outstandingChangesForPath.get(path);
        //...
}

public void processRequest(Request request) {
    synchronized (zks.outstandingChanges) {
        // Need to process local session requests
        // 修改本地内存（DataTree）中的节点信息
        rc = zks.processTxn(request);
        //...
}
```



##### 4）数据 有快照 + 日志文件保证数据安全



数据可以从日志追加记录中 或者 快照文件 进行恢复，见FileTxnSnapLog.restore() 中的 fastForwardFromEdits方法

```
/**
 * This function will fast forward the server database to have the latest
 * transactions in it.  This is the same as restore, but only reads from
 * the transaction logs and not restores from a snapshot.
 * @param dt the datatree to write transactions to.
 * @param sessions the sessions to be restored.
 * @param listener the playback listener to run on the
 * database transactions.
 * @return the highest zxid restored.
 * @throws IOException
 */
public long fastForwardFromEdits(DataTree dt, Map<Long, Integer> sessions,
                                 PlayBackListener listener) throws IOException {
    TxnIterator itr = txnLog.read(dt.lastProcessedZxid+1);
    long highestZxid = dt.lastProcessedZxid;
    TxnHeader hdr;
    try {
        // 按事务日志的zxid顺序解析所有文件
        while (true) {
            // iterator points to
            // the first valid txn when initialized
            hdr = itr.getHeader();
            if (hdr == null) {
                //empty logs
                return dt.lastProcessedZxid;
            }
            // 更新zxid并处理事务
            if (hdr.getZxid() < highestZxid && highestZxid != 0) {
                LOG.error("{}(highestZxid) > {}(next log) for type {}",
                        highestZxid, hdr.getZxid(), hdr.getType());
            } else {
                highestZxid = hdr.getZxid();
            }
            try {
                processTransaction(hdr,dt,sessions, itr.getTxn());
            } catch(KeeperException.NoNodeException e) {
               throw new IOException("Failed to process transaction type: " +
                     hdr.getType() + " error: " + e.getMessage(), e);
            }
            // 监听器监听事务日志恢复信息
            listener.onTxnLoaded(hdr, itr.getTxn());
            if (!itr.next())
                break;
        }
    } finally {
        if (itr != null) {
            itr.close();
        }
    }
    return highestZxid;
}
```



##### 5）acl 权限安全



每个节点都会有对应的权限，新节点是ALL权限

```
public interface Perms {
    int READ = 1 << 0;

    int WRITE = 1 << 1;

    int CREATE = 1 << 2;

    int DELETE = 1 << 3;

    int ADMIN = 1 << 4;

    int ALL = READ | WRITE | CREATE | DELETE | ADMIN;
}
```



执行相应的事件操作时会检查节点权限

```
// 校验父节点是否有创建节点的权限
checkACL(zks, parentRecord.acl, ZooDefs.Perms.CREATE, request.authInfo);

/**
 * Grant or deny authorization to an operation on a node as a function of:
 *
 * @param zks: not used.
 * @param acl:  set of ACLs for the node
 * @param perm: the permission that the client is requesting
 * @param ids:  the credentials supplied by the client
 */
static void checkACL(ZooKeeperServer zks, List<ACL> acl, int perm,
                     List<Id> ids) throws KeeperException.NoAuthException {
    if (skipACL) {
        return;
    }
    if (acl == null || acl.size() == 0) {
        return;
    }
    for (Id authId : ids) {
        if (authId.getScheme().equals("super")) {
            return;
        }
    }
    for (ACL a : acl) {
        Id id = a.getId();
        if ((a.getPerms() & perm) != 0) {
            if (id.getScheme().equals("world")
                    && id.getId().equals("anyone")) {
                return;
            }
            AuthenticationProvider ap = ProviderRegistry.getProvider(id
                    .getScheme());
            if (ap != null) {
                for (Id authId : ids) {
                    if (authId.getScheme().equals(id.getScheme())
                            && ap.matches(authId.getId(), id.getId())) {
                        return;
                    }
                }
            }
        }
    }
    throw new KeeperException.NoAuthException();
}
```





#### **5、zk的Watch机制？**



##### 1）watch的数据存储



watcher的关联path存储在WatchManager中的两个HashMap中，watchTable 是 path 和 watcher的一对多关系，watch2Paths 是 watcher和path的一对多关系，两者在不同的场景下搭配使用

```
private final HashMap<String, HashSet<Watcher>> watchTable =
    new HashMap<String, HashSet<Watcher>>();

private final HashMap<Watcher, HashSet<String>> watch2Paths =
    new HashMap<Watcher, HashSet<String>>();
```



添加Watcher的核心方法见WatcherManager.addWatch方法，核心也就分别向watchTable 和 watch2Paths中填充内容

```
synchronized void addWatch(String path, Watcher watcher) {
    HashSet<Watcher> list = watchTable.get(path);
    if (list == null) {
        // don't waste memory if there are few watches on a node
        // rehash when the 4th entry is added, doubling size thereafter
        // seems like a good compromise
        list = new HashSet<Watcher>(4);
        watchTable.put(path, list);
    }
    list.add(watcher);

    HashSet<String> paths = watch2Paths.get(watcher);
    if (paths == null) {
        // cnxns typically have many watches, so use default cap here
        paths = new HashSet<String>();
        watch2Paths.put(watcher, paths);
    }
    paths.add(path);
}
```



添加Watcher的场景有很多种，常见的比如 获取节点数据（getData）、获取节点状态（statNode）、获取子节点（getChildern） 和 直接对节点添加Watch，除直接对节点添加Watch行为外，其他操作均有客户端有选择性的发起，比如我希望实时获取节点数据，即节点数据能在修改的时候通知到我，这一点可以用作 全局配置项 或者 服务发现 的场景中；

直接添加Watch的行为 我们常见于分布式锁，分布式锁会在zk上创建临时有序节点（EPHEMERAL_SEQUENTIAL），当客户端断开连接时节点会自动删除（放弃锁），较大的临时节点存在时（锁占有）可以对该节点进行Watch，该临时节点主动或被动删除后会通知到我（获取锁），这个可以实现公平锁；非公平锁 即直接对父节点进行 Watch，当子节点发生Delete操作时获取到通知 进行抢占锁；当然在并发的情况下由zk保证并发操作的有序性 和 线程安全；



看下的相关代码，以获取节点数据为例

```
case OpCode.getData: {
    lastOp = "GETD";
    GetDataRequest getDataRequest = new GetDataRequest();
    // 将客户端request里的请求 内容 赋给 GetDataRequest
    ByteBufferInputStream.byteBuffer2Record(request.request,
            getDataRequest);
    DataNode n = zks.getZKDatabase().getNode(getDataRequest.getPath());
    if (n == null) {
        throw new KeeperException.NoNodeException();
    }
    PrepRequestProcessor.checkACL(zks, zks.getZKDatabase().aclForNode(n),
            ZooDefs.Perms.READ,
            request.authInfo);
    Stat stat = new Stat();
    // 加入 客户端请求中带有watch参数，则将当前的serer连接视为watcher进行注册
    byte b[] = zks.getZKDatabase().getData(getDataRequest.getPath(), stat,
            getDataRequest.getWatch() ? cnxn : null);
    rsp = new GetDataResponse(b, stat);
    break;
```



这里的cnxn代表当前连接zkServer的连接信息，如果是NIO模式下就是一条Select socket连接

```
private void readRequest() throws IOException {
    // NIO模式下 this代指NIOServerCnxn
    zkServer.processPacket(this, incomingBuffer);
}
```



##### 2）哪些情况下会触发watch？



触发watch的场景大致分成两种，节点自身变化 和 节点数据变化，分别对应DataTree中的childWatches 和 dataWatches

```
// 关心节点数据变化
private final WatchManager dataWatches = new WatchManager();

// 关心节点自身变化
private final WatchManager childWatches = new WatchManager();
```



正常watch事件触发是在内存中的DataTree修改完成后发生。以删除节点为例，见DataTree.deleteNode()

```
public void deleteNode(String path, long zxid)
        throws KeeperException.NoNodeException {
    //...不重要
    // 数据变化 触发DataWatch的process方法
    Set<Watcher> processed = dataWatches.triggerWatch(path,EventType.NodeDeleted);
    // 节点变化 触发ChildWatch的process方法，这里剔除了数据变化触发的Watcher
    childWatches.triggerWatch(path, EventType.NodeDeleted, processed);
    childWatches.triggerWatch("".equals(parentName) ? "/" : parentName,EventType.NodeChildrenChanged);
}
```



triggerWatch即查询 对节点感兴趣的Watchers，发一条短信（WatchedEvent）通知他们，通知的内容仅包括 通知状态、事件类型 和 节点path

```
public class WatchedEvent {
    // 通知状态
    final private KeeperState keeperState;
    // 事件类型
    final private EventType eventType;
    // 节点path
    private String path;
}

Set<Watcher> triggerWatch(String path, EventType type, Set<Watcher> supress) {
    WatchedEvent e = new WatchedEvent(type,
            KeeperState.SyncConnected, path);
    HashSet<Watcher> watchers;
    synchronized (this) {
        watchers = watchTable.remove(path);
        if (watchers == null || watchers.isEmpty()) {
            if (LOG.isTraceEnabled()) {
                ZooTrace.logTraceMessage(LOG,
                        ZooTrace.EVENT_DELIVERY_TRACE_MASK,
                        "No watchers for " + path);
            }
            return null;
        }
        for (Watcher w : watchers) {
            HashSet<String> paths = watch2Paths.get(w);
            if (paths != null) {
                paths.remove(path);
            }
        }
    }
    for (Watcher w : watchers) {
        if (supress != null && supress.contains(w)) {
            continue;
        }
        w.process(e);
    }
    return watchers;
}
```



##### 3）触发watch后怎么反馈到监听的客户端？



这里以NIO模式下的服务端为例，对应Watcher（NIOServerCnxn）的WatchEvent通知行为

```
public void process(WatchedEvent event) {
    ReplyHeader h = new ReplyHeader(-1, -1L, 0);
    if (LOG.isTraceEnabled()) {
        ZooTrace.logTraceMessage(LOG, ZooTrace.EVENT_DELIVERY_TRACE_MASK,
                                 "Deliver event " + event + " to 0x"
                                 + Long.toHexString(this.sessionId)
                                 + " through " + this);
    }

    // Convert WatchedEvent to a type that can be sent over the wire
    WatcherEvent e = event.getWrapper();

    sendResponse(h, e, "notification");
}

sendResponse会将响应信息放到outgoingBuffer缓冲队列中
private final Queue<ByteBuffer> outgoingBuffers =
    new LinkedBlockingQueue<ByteBuffer>();

/**
 * sendBuffer pushes a byte buffer onto the outgoing buffer queue for
 * asynchronous writes.
 */
public void sendBuffer(ByteBuffer bb) {
    if (LOG.isTraceEnabled()) {
        LOG.trace("Add a buffer to outgoingBuffers, sk " + sk
                  + " is valid: " + sk.isValid());
    }
    outgoingBuffers.add(bb);
    // 有响应信息了，唤醒selector线程，让它工作（假如不在工作）
    requestInterestOpsUpdate();
}
```



接下的事情就交给Selector线程 和 Worker线程了，Selector线程select出内容后 交给Worker线程处理，Worker 会将outgoingBuffer的内容进行输出





#### **6、zk的会话机制？**



##### 1）客户端连接数限制



先简单总结 最大客户端连接数为60，超过60则拒绝连接；对存在的客户端连接有会话时间限制（默认10s），10s内无任何消息处理（select）则被ExpireThread清理掉；当客户端有消息处理（select）时则给它续命（默认10s）

```
protected int maxClientCnxns = 60;
```



客户端连接数过大时则拒绝连接，被AcceptThread拒绝

```
private boolean doAccept() {
    boolean accepted = false;
    SocketChannel sc = null;
    try {
        sc = acceptSocket.accept();
        accepted = true;
        InetAddress ia = sc.socket().getInetAddress();
        int cnxncount = getClientCnxnCount(ia);
        // 默认为60
        if (maxClientCnxns > 0 && cnxncount >= maxClientCnxns) {
            throw new IOException("Too many connections from " + ia
                    + " - max is " + maxClientCnxns);
        }
//...
}
```



SelectorThread有新客户端连接请求时封装成NIOServerCnxn 进行管理，并关联（attach）到SelectKey上

```
/**
 * Iterate over the queue of accepted connections that have been
 * assigned to this thread but not yet placed on the selector.
 */
private void processAcceptedConnections() {
    SocketChannel accepted;
    while (!stopped && (accepted = acceptedQueue.poll()) != null) {
        // 选择键维护了通道和选择器之间的关联，可以通过选择键获取Channel或Selector，键对象表示一种特殊的关联关系
        SelectionKey key = null;
        try {
            key = accepted.register(selector, SelectionKey.OP_READ);
            NIOServerCnxn cnxn = createConnection(accepted, key, this);
            key.attach(cnxn);
            // 添加进 cnxns中
            addCnxn(cnxn);
        } catch (IOException e) {
            // register, createConnection
            cleanupSelectionKey(key);
            fastCloseSock(accepted);
        }
    }
}
```



ExpireThread清理掉过期会话，关闭客户端连接

```
private class ConnectionExpirerThread extends ZooKeeperThread {

    public void run() {
        try {
            while (!stopped) {
                long waitTime = cnxnExpiryQueue.getWaitTime();
                if (waitTime > 0) {
                    Thread.sleep(waitTime);
                    continue;
                }
                for (NIOServerCnxn conn : cnxnExpiryQueue.poll()) {
                    conn.close();
                }
            }

        } catch (InterruptedException e) {
            LOG.info("ConnnectionExpirerThread interrupted");
        }
    }
}
```



SelectorTrhead有客户端请求时修改客户端的会话时间（状态）

```
/**
 * Schedule I/O for processing on the connection associated with
 * the given SelectionKey. If a worker thread pool is not being used,
 * I/O is run directly by this thread.
 */
private void handleIO(SelectionKey key) {
    IOWorkRequest workRequest = new IOWorkRequest(this, key);
    NIOServerCnxn cnxn = (NIOServerCnxn) key.attachment();

    // Stop selecting this key while processing on its
    // connection
    cnxn.disableSelectable();
    key.interestOps(0);
    //更新客户端的连接状态
    touchCnxn(cnxn);
    workerPool.schedule(workRequest);
}

/**
 * Add or update cnxn in our cnxnExpiryQueue
 * @param cnxn
 */
public void touchCnxn(NIOServerCnxn cnxn) {
    //默认session有效时长为10s
    cnxnExpiryQueue.update(cnxn, cnxn.getSessionTimeout());
}
```



##### 2）客户端会话跟踪



会话管理 和 上面客户端连接管理的区别在于 出发点不一样，客户端连接管理 是出于服务端性能考虑，关闭不必要 或 空闲的客户端连接，直接从socket层面给它close掉；会话管理是 出于业务安全考虑，更多的偏向于一种权限管理，比如验证会话的有效性，会话是否超时等；两者的共同之处在于都借助于使用ExpiryQueue来清理失效连接，当连接有活跃请求时又会touch连接（续费）。



Session是 ZooKeeper中的会话实体,代表了一个客户端会话。其包含以下4个基本属性。

sessionID:会话ID,用来唯一标识一个会话,每次客户端创建新会话的时候,ZooKeeper都会为其分配一个全局唯一的 sessionID。

TimeOut:会话超时时间。客户端在构造 ZooKeeper实例的时候,会配置一个sessiontimeout参数用于指定会话的超时时间。ZooKeeper客户端向服务器发送这个超时时间后,服务器会根据自己的超时时间限制最终确定会话的超时时间。

TickTime:下次会话超时时间点。为了便于 ZooKeeper对会话实行“分桶策略”管理,同时也是为了高效低耗地实现会话的超时检查与清理, ZooKeeper会为每个会话标记一个下次会话超时时间点。 TickTime是一个13位的long型数据,其值接近于当前时间加上 Time Out,但不完全相等。关于 TickTime的计算方式,将在“分桶策略”部分做详细讲解。

isClosing:该属性用于标记一个会话是否已经被关闭。通常当服务端检测到一个会话已经超时失效的时候,会将该会话的 isClosing属性标记为“已关闭”,这样就能确保不再处理来自该会话的新请求了。



这里分桶策略就是将 会话 根据 expireTime进行分桶管理，然后Leader服务器在运行期间会定时地对不同的分桶进行会话超时检査。



![img](http://pcc.huitogo.club/7aae462cff2f5041d2bf75e628e6d134)



**session的创建**

服务端对于客户端的“会话创建”请求的处理,大体可以分为四大步骤,分别是处理ConnectRequest请求、会话创建、处理器链路处理和会话响应。在 ZooKeeper服务端,首先将会由NI0 Servercnxn来负责接收来自客户端的“会话创建”请求,并反序列化出ConnectRequest请求,然后根据 ZooKeeper服务端的配置完成会话超时时间的协商。随后, Session tracker将会为该会话分配一个 sessionID,并将其注册到sessionsById和 sessionsWithTimeout中去,同时进行会话的激活。之后,该“会话请求”还会在 ZooKeeper服务端的各个请求处理器之间进行顺序流转,最终完成会话的创建。

```
public void processConnectRequest(ServerCnxn cnxn, ByteBuffer incomingBuffer) throws IOException {
    BinaryInputArchive bia = BinaryInputArchive.getArchive(new ByteBufferInputStream(incomingBuffer));
    ConnectRequest connReq = new ConnectRequest();
    connReq.deserialize(bia, "connect");
    //...
    int sessionTimeout = connReq.getTimeOut();
    byte passwd[] = connReq.getPasswd();
    int minSessionTimeout = getMinSessionTimeout();
    if (sessionTimeout < minSessionTimeout) {
        sessionTimeout = minSessionTimeout;
    }
    int maxSessionTimeout = getMaxSessionTimeout();
    if (sessionTimeout > maxSessionTimeout) {
        sessionTimeout = maxSessionTimeout;
    }
    cnxn.setSessionTimeout(sessionTimeout);
    // We don't want to receive any packets until we are sure that the
    // session is setup
    cnxn.disableRecv();
    long sessionId = connReq.getSessionId();
    if (sessionId == 0) {
        long id = createSession(cnxn, passwd, sessionTimeout);
    } else {
        long clientSessionId = connReq.getSessionId();
        if (serverCnxnFactory != null) {
            serverCnxnFactory.closeSession(sessionId);
        }
        if (secureServerCnxnFactory != null) {
            secureServerCnxnFactory.closeSession(sessionId);
        }
        cnxn.setSessionId(sessionId);
        reopenSession(cnxn, sessionId, passwd, sessionTimeout);
    }
}
```



主要关注sessionId的生成，在客户端没有提供的情况下 且是初始化连接则需要zk服务端自行创建唯一会话id，默认采用的是自增的方式，但自增的初始值是 serverId + 时间戳的组合方式

```
private final AtomicLong nextSessionId = new AtomicLong();

/**
 * Generates an initial sessionId. High order byte is serverId, next 5
 * 5 bytes are from timestamp, and low order 2 bytes are 0s.
 */
public static long initializeNextSession(long id) {
    long nextSid;
    nextSid = (Time.currentElapsedTime() << 24) >>> 8;
    nextSid =  nextSid | (id <<56);
    if (nextSid == EphemeralType.CONTAINER_EPHEMERAL_OWNER) {
        ++nextSid;  // this is an unlikely edge case, but check it just in case
    }
    return nextSid;
}

public long createSession(int sessionTimeout) {
    // 自增
    long sessionId = nextSessionId.getAndIncrement();
    addSession(sessionId, sessionTimeout);
    return sessionId;
}
```



存储session的是两个数据结构，sessionsWithTimeout 和 sessionsById，前者记录session的超时时间，后者记录session的详细信息，添加session如下：

```
public synchronized boolean addSession(long id, int sessionTimeout) {
    sessionsWithTimeout.put(id, sessionTimeout);

    boolean added = false;

    SessionImpl session = sessionsById.get(id);
    if (session == null){
        session = new SessionImpl(id, sessionTimeout);
    }

    // findbugs2.0.3 complains about get after put.
    // long term strategy would be use computeIfAbsent after JDK 1.8
    SessionImpl existedSession = sessionsById.putIfAbsent(id, session);

    if (existedSession != null) {
        session = existedSession;
    } else {
        added = true;
        LOG.debug("Adding session 0x" + Long.toHexString(id));
    }

    if (LOG.isTraceEnabled()) {
        String actionStr = added ? "Adding" : "Existing";
        ZooTrace.logTraceMessage(LOG, ZooTrace.SESSION_TRACE_MASK,
                "SessionTrackerImpl --- " + actionStr + " session 0x"
                + Long.toHexString(id) + " " + sessionTimeout);
    }
    // 激活session（充值）
    updateSessionExpiry(session, sessionTimeout);
    return added;
}
```



这里session激活也是利用ExpiryQueue，同样session失效会话的清理也是类似借助线程完成

```
@Override
public void run() {
    try {
        while (running) {
            long waitTime = sessionExpiryQueue.getWaitTime();
            if (waitTime > 0) {
                Thread.sleep(waitTime);
                continue;
            }

            for (SessionImpl s : sessionExpiryQueue.poll()) {
                setSessionClosing(s.sessionId);
                expirer.expire(s);
            }
        }
    } catch (InterruptedException e) {
        handleException(this.getName(), e);
    }
    LOG.info("SessionTrackerImpl exited loop!");
}
```



session创建完之后会发起一条CreateSession的请求交给处理器链处理

```
long createSession(ServerCnxn cnxn, byte passwd[], int timeout) {
    if (passwd == null) {
        // Possible since it's just deserialized from a packet on the wire.
        passwd = new byte[0];
    }
    // 自增的sessionId
    long sessionId = sessionTracker.createSession(timeout);
    Random r = new Random(sessionId ^ superSecret);
    // 加密密码
    r.nextBytes(passwd);
    ByteBuffer to = ByteBuffer.allocate(4);
    to.putInt(timeout);
    cnxn.setSessionId(sessionId);
    Request si = new Request(cnxn, sessionId, 0, OpCode.createSession, to, null);
    setLocalSessionFlag(si);
    submitRequest(si);
    return sessionId;
}
```



其中预处理器 和 最终处理器均执行的addSession()方法

```
case OpCode.createSession:
    request.request.rewind();
    int to = request.request.getInt();
    request.setTxn(new CreateSessionTxn(to));
    request.request.rewind();
    if (request.isLocalSession()) {
        // This will add to local session tracker if it is enabled
        zks.sessionTracker.addSession(request.sessionId, to);
    } else {
        // Explicitly add to global session if the flag is not set
        zks.sessionTracker.addGlobalSession(request.sessionId, to);
    }
    zks.setOwner(request.sessionId, request.getOwner());
    break;
```



这里我的理解是 为了让session保持最佳有效时长，避免因为连接请求处理时间过长导致会话失效，毕竟客户端发起ping请求也得是 连接建立完之后



request的owner 指的是发起请求来源，这里来源是 客户端请求即ServerCnxn.me，还可能是follwer发起的请求

```
// setowner as the leader itself, unless updated
// via the follower handlers
setOwner(sessionId, ServerCnxn.me);
```



当客户端有发起请求的时候会对重新激活会话

```
public void submitRequest(Request si) {
    //...
    // 客户端有请求来了，激活会话
    touch(si.cnxn);
    //...
}

void touch(ServerCnxn cnxn) throws MissingSessionException {
    if (cnxn == null) {
        return;
    }
    long id = cnxn.getSessionId();
    int to = cnxn.getSessionTimeout();
    if (!sessionTracker.touchSession(id, to)) {
        throw new MissingSessionException(
                "No session with sessionid 0x" + Long.toHexString(id)
                + " exists, probably expired and removed");
    }
}
```



重新激活会话 更新expiryQueue 中会话的下次失效时间，默认3s

```
synchronized public boolean touchSession(long sessionId, int timeout) {
    SessionImpl s = sessionsById.get(sessionId);

    if (s == null) {
        logTraceTouchInvalidSession(sessionId, timeout);
        return false;
    }

    if (s.isClosing()) {
        logTraceTouchClosingSession(sessionId, timeout);
        return false;
    }

    updateSessionExpiry(s, timeout);
    return true;
}
```



会话一个重要的使用场景就是对客户端发起的请求进行校验，比如在预处理器中处理Delete操作之前

```
case OpCode.delete:
    zks.sessionTracker.checkSession(request.sessionId, request.getOwner());
```



校验会话一方面判断sessionId是否存在（存活），另一方面判断请求来源是否正确

```
public synchronized void checkSession(long sessionId, Object owner)
        throws KeeperException.SessionExpiredException,
        KeeperException.SessionMovedException,
        KeeperException.UnknownSessionException {
    LOG.debug("Checking session 0x" + Long.toHexString(sessionId));
    SessionImpl session = sessionsById.get(sessionId);

    if (session == null) {
        throw new KeeperException.UnknownSessionException();
    }

    if (session.isClosing()) {
        throw new KeeperException.SessionExpiredException();
    }

    if (session.owner == null) {
        session.owner = owner;
    } else if (session.owner != owner) {
        throw new KeeperException.SessionMovedException();
    }
}
```