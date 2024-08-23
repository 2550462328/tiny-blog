AQS原理分析
2024-08-22
AQS核心思想是，如果被请求的共享资源空闲，则将当前请求资源的线程设置为有效的工作线程，并且将共享资源设置为锁定状态。如果被请求的共享资源被占用，那么就需要一套线程阻塞等待以及被唤醒时锁分配的机制，这个机制AQS是用CLH队列锁实现的，即将暂时获取不到锁的线程加入到队列中
02.jpg
Java基础
huizhang43

之前“ReentrantLock源码分析”一节简单讲了AQS的概述以及ReentrantLock是怎么利用AQS实现独占锁的，本节重点讲AQS的原理和补充说明ReentrantLock的condition部分

**AQS核心思想是，如果被请求的共享资源空闲，则将当前请求资源的线程设置为有效的工作线程，并且将共享资源设置为锁定状态。如果被请求的共享资源被占用，那么就需要一套线程阻塞等待以及被唤醒时锁分配的机制，这个机制AQS是用CLH队列锁实现的，即将暂时获取不到锁的线程加入到队列中**。



AQS提供了两种方式来获取资源，一种是独占模式，一种是共享模式。

使用AQS框架需要定义一个类继承AbstractQueuedSynchronizer类，重写其中的方法，主要实现的是对共享资源state的获取和释放方式，至于具体线程等待队列的维护（如获取资源失败入队，唤醒出队等）已经由AQS封装好的。

1）对于独占模式，需要重写tryAcquire(arg) ，tryRelease(int arg)方法。

2）对于共享模式，需要重写tryAcquireShared(arg) ，tryReleaseShared(int arg)方法。

事实上AQS中除了这些方法外其他方法都是final的，无法被其他类使用。



#### **1、LockSupport**

之前在看ReentrantLock.lock和ReentrantLock.unlock方法中可以看到最后阻塞线程和激活线程使用的是LockSupport.park()和LockSupport.unpark()方法，那么LockSupport是什么？

我认为LockSupport相当于Lock的一个工具类，主要用途就是**实现对线程的阻塞和解除对线程的阻塞**

park()和unpark()的原理是基于“许可证”（一种信号量机制），park的时候消耗一个“许可证”，unpark()的时候会提供一个“许可证”（注意多次不会叠加），当许可证为0的时候，线程就会阻塞了，等待发放“许可证”。



##### **（1）park方法**

###### 1）park()

```
3.   public static void park() {  

4.       UNSAFE.park(false, 0L);  

5.   }  

6.  //unsafe.class中  

7.  public native void park(boolean var1, long var2);  
```

调用jvm的本地方法将当前线程阻塞。



###### 2）park(Object blocker)

```
2.  public static void park(Object blocker) {  

3.      Thread t = Thread.currentThread();  

4.      setBlocker(t, blocker);  

5.      UNSAFE.park(false, 0L);  

6.      setBlocker(t, null);  

7.  }  

8.  private static void setBlocker(Thread t, Object arg) {  

9.      UNSAFE.putObject(t, parkBlockerOffset, arg);  

10. }  
```

这里在线程阻塞前和线程阻塞后都会setBlocker()，但是setBlocker有什么用？为什么设置两次？

这里第一个setBlocker就是设置当前Thread对象中的parkBlocker变量，**用来记录线程被阻塞时被谁阻塞的,用于线程监控和分析工具来定位原因的**。

第二个setBlocker是进行还原操作，防止另一个Thread获取到了错误了parkBlocker。



获取这个blocker采用的是内存偏移量方式，查找parkBlocker字段相对于Thread的内存偏移量，然后根据这个内存偏移量去查找变量值

```
1.  public static Object getBlocker(Thread t) {  

2.      if (t == null)  

3.          throw new NullPointerException();  

4.      return UNSAFE.getObjectVolatile(t, parkBlockerOffset);  

5.  }  

6.  parkBlockerOffset = UNSAFE.objectFieldOffset(tk.getDeclaredField("parkBlocker"));  
```



为什么要基于内存的方式去设置/获取blocker？直接写个方法不就行了？

parkBlocker就是在线程处于阻塞的情况下才被赋值。线程都已经被阻塞了,如果不通过这种内存的方法,而是直接调用线程内的方法,线程是不会回应调用的。



关于blocker做的小案例，获取blocker的变换情况

```
1.  public static void main(String[] args) throws InterruptedException {  

2.      Thread thread = Thread.currentThread();  

3.      Thread thread1 = new Thread(() -> {  

4.          try {  

5.              TimeUnit.SECONDS.sleep(1);  

6.          } catch (InterruptedException e) {  

7.          }  

8.          System.out.println(thread.getName() + "before block : block info is " + LockSupport.getBlocker(thread));  

9.          LockSupport.unpark(thread);  

10.     });  

11.     thread1.start();  

12.     LockSupport.park(new String("aa"));  

13.     System.out.println(thread.getName() + "after block : block info is " + LockSupport.getBlocker(thread));  

14. }  
```



输出

```
1.  mainbefore block : block info is blocker  

2.  mainafter block : block info is null  
```



###### 3）parkNanos(Object blocker, long nanos)

```
1.  public static void parkNanos(Object blocker, long nanos) {  

2.      if (nanos > 0) {  

3.          Thread t = Thread.currentThread();  

4.          setBlocker(t, blocker);  

5.          UNSAFE.park(false, nanos);  

6.          setBlocker(t, null);  

7.      }  

8.  }  
```

和park(Objectblocker)的区别就是多个限时操作，在规定时间内没有获取到“许可证”会直接返回。



park在下面三种情况会直接返回

- 调用线程被中断,则park方法会返回
- unpark方法先于park调用会直接返回
- 其他某个线程将当前线程作为目标调用 unpark
- park方法还可以在其他任何时间"毫无理由"地返回,因此**通常必须在重新检查返回条件的循环里调用此方法**。从这个意义上说,park是“忙碌等待”的一种优化,它不会浪费这么多的时间进行自旋,但是必须将它与 unpark配对使用才更高效



##### （2）unpark

```
2.  public static void unpark(Thread thread) {  

3.      if (thread != null)  

4.          UNSAFE.unpark(thread);  

5.  }  

6.  //unsafe.class中  

7.  public native void unpark(Object var1);  
```

解除指定线程的阻塞，必须指定线程。



park()和unpark()不会有“Thread.suspend和Thread.resume所可能引发的死锁”问题,由于许可证的存在，调用park 的线程和另一个试图将其 unpark 的线程之间的竞争将保持活性。



##### （3）park/unpark和wait/nofity的区别

首先对比一下调用park和wait后通过jstack打印出来的堆栈情况

![img](http://pcc.huitogo.club/f52b1a35236229069c79db578b44eff2)

![img](http://pcc.huitogo.club/6a43d4c94b4b97c81f9fde8fd16b807c)



两者区别如下：

1）LockSuport主要是针对Thread进行阻塞处理,可以指定阻塞队列的目标对象,每次可以指定具体的线程唤醒。Object.wait()是以对象为纬度,阻塞当前的线程和唤醒单个(随机)或者所有线程。

2）Thead在调用wait之前，当前线程必须先获得该对象的监视器(synchronized)，被唤醒之后需要重新获取到监视器才能继续执行.而LockSupport可以随意进行park或者unpark。

3）park时遇到interrupt会直接返回继续执行，而wait的时候遇到interrupt会抛出异常。



#### **2、Node**

AQS维护了一个FIFO的双向队列，具体就体现在Node类的head和tail两个变量，顾名思义，head保存了头节点，tail保存了尾节点。

```
1.  private transient volatile Node head;  

2.  private transient volatile Node tail;
```



Node类中的SHARED是用来标记该线程是获取共享资源时被放入等待队列，EXCLUSIVE用来标记该线程是获取独占资源时被放入等待队列（就是上面的双向队列）。我们可以看出Node类其实就是保存了放入等待队列的线程，而有的线程是因为获取共享资源失败放入等待队列的，而有的线程是因为获取独占资源失败而被放入等待队列的，所以这里需要有一个标记去区分。

```
1.  static final Node SHARED = new Node();  

2.  static final Node EXCLUSIVE = null; 
```



在Node类中，还有一个字段：waitStatus，它有五个取值，分别是：

- SIGNAL：值为-1，当前节点在入队后、进入休眠状态前，应确保将其prev节点类型改为SIGNAL，以便后者取消或释放时将当前节点唤醒。
- CANCELLED：值为1，被取消的，在等待队列中等待的线程超时或被中断，该状态的节点将会被清除。
- CONDITION：值为-2，该节点处于条件队列中，当其他线程调用了Condition的signal()方法后，节点转移到AQS的等待队列中，特别要注意的是，条件队列和AQS的等待队列并不是一回事。
- PROPAGATE：值为-3。用处暂时不清楚。
- 0：默认值。



#### **3、ConditionObject**

ConditionObject实现了Condition接口，Condition必须被绑定到一个独占锁上使用，在ReentrantLock中，有一个newCondition方法

ConditionObject帮助AQS实现了类似wait/notify的功能，帮助已经获取到lock的线程在没有达到条件的时候挂起（await），在条件满足后被通知（signal）。

因此那些被挂起的线程也要用一个队列来装载它们，这个队列叫**条件队列**。

需要注意的是**条件队列是一条单向队列**，它是通过Node类中的nextWaiter进行连接。



条件队列和之前的双向同步队列的关系如下：

当节点从同步队列进入条件队列（condition.await()）

![img](http://pcc.huitogo.club/e4d7cfa7a93258529322f0c15099ab36)



当节点从条件队列进入同步队列(condition.signal())

![img](http://pcc.huitogo.club/b679dfe02ef1d9e7f65c3fa373ccc74c)



下面看一下它的关键方法

##### **（1）await()**

await就是获取锁的线程让出锁然后将自己加入条件队列并阻塞，源码如下

```
1.  public final void await() throws InterruptedException {  

2.      if (Thread.interrupted())  

3.          throw new InterruptedException();  

4.      Node node = addConditionWaiter();  

5.      int savedState = fullyRelease(node);  

6.      int interruptMode = 0;  

7.      while (!isOnSyncQueue(node)) {  

8.          LockSupport.park(this);  

9.          if ((interruptMode = checkInterruptWhileWaiting(node)) != 0)  

10.             break;  

11.     }  

12.     if (acquireQueued(node, savedState) && interruptMode != THROW_IE)  

13.         interruptMode = REINTERRUPT;  

14.     if (node.nextWaiter != null) // clean up if cancelled  

15.         unlinkCancelledWaiters();  

16.     if (interruptMode != 0)  

17.         reportInterruptAfterWait(interruptMode);  

18. }  
```



根据源码来思考它是怎么实现以上步骤的

首先是将当前线程的节点加入条件队列，addConditionWaiter

```
1.  private Node addConditionWaiter() {  

2.      Node t = lastWaiter;  

3.      // If lastWaiter is cancelled, clean out.  

4.      if (t != null && t.waitStatus != Node.CONDITION) {  

5.          unlinkCancelledWaiters();  

6.          t = lastWaiter;  

7.      }  

8.      Node node = new Node(Thread.currentThread(), Node.CONDITION);  

9.      if (t == null)  

10.         firstWaiter = node;  

11.     else  

12.         t.nextWaiter = node;  

13.     lastWaiter = node;  

14.     return node;  

15. }
```

先clean up了一下CANCALLED节点，保证新建节点的上一个节点不是CANCELLED的，接着放在队列最后面。



然后是当前线程让出所持有的锁，fullyRelease方法

```
1.  final int fullyRelease(Node node) {  

2.      boolean failed = true;  

3.      try {  

4.          int savedState = getState();  

5.          if (release(savedState)) {  

6.              failed = false;  

7.              return savedState;  

8.          } else {  

9.              throw new IllegalMonitorStateException();  

10.         }  

11.     } finally {  

12.         if (failed)  

13.             node.waitStatus = Node.CANCELLED;  

14.     }  

15. }  
```

调用的主要是之前讲unlock方法时用到的release方法，将锁的owner清空后唤醒后一个SIGNAL的节点，需要注意的是直接将state清零而不是减一操作了，所以叫fullRelease。



不出意外此时节点已经进入条件队列，但在阻塞之前还是判断一下比较好，isOnSyncQueue方法

```
1.  final boolean isOnSyncQueue(Node node) {  

2.      if (node.waitStatus == Node.CONDITION || node.prev == null)   

3.          return false;  

4.      if (node.next != null) // If has successor, it must be on queue  

5.          return true;  

6.      return findNodeFromTail(node);  

7.  }  
```

从节点状态和prev/next角度简单判断，如果都不满足就在同步队列里面遍历查询，**但是这里为什么从尾部开始遍历？**



确定该节点已经进入条件队列了，将它阻塞（LockSupport.park）

当它醒过来的时候，先看看它是不是因为被interrupted吵醒了，checkInterruptWhileWaiting方法

```
1.  private int checkInterruptWhileWaiting(Node node) {  

2.      return Thread.interrupted() ?  

3.          (transferAfterCancelledWait(node) ? THROW_IE : REINTERRUPT) : 0;  

4.  }  

5.  final boolean transferAfterCancelledWait(Node node) {  

6.      if (compareAndSetWaitStatus(node, Node.CONDITION, 0)) {  

7.          enq(node);  

8.          return true;  

9.      }  

10.     while (!isOnSyncQueue(node))  

11.         Thread.yield();  

12.     return false;  

13. }  
```

被interrupted吵醒后判断后续的处理应该是抛出InterruptedException还是重新中断，判断的标准是**在线程中断的时候是否有signal方法调用**

1）如果compareAndSetWaitStatus(node, Node.CONDITION,0)执行成功，则说明中断发生时，没有signal的调用，因为signal方法会将状态设置为0。

2）如果第1步执行成功，则将node添加到Sync队列中，并返回true，表示中断在signal之前；

3）如果第1步失败，则检查当前线程的node是否已经在Sync队列中了，如果不在Sync队列中，则让步给其他线程执行，直到当前的node已经被signal方法添加到Sync队列中，然后返回false，表示中断前没有signal执行。



**被interrupted中断或者正常唤醒并加入同步队列**后，当前线程尝试获取锁acquireQueued(node,savedState)，只有获取到了锁这个方法才会返回，返回值代表当前线程有没有被中断，修改interruptMode的值，如果有中断（interruptMode!=0）然后执行reportInterruptAfterWait方法

```
1.  private void reportInterruptAfterWait(int interruptMode)  

2.      throws InterruptedException {  

3.      if (interruptMode == THROW_IE)  

4.          throw new InterruptedException();  

5.      else if (interruptMode == REINTERRUPT)  

6.          selfInterrupt();  

7.  }  
```



##### **（2）awaitNanos(long nanosTimeout)**

awaitNanos指的是有限等待，**在规定时间内没有被唤醒（中断或者正常），就会被放回到同步队列**

```
1.  public final long awaitNanos(long nanosTimeout)  

2.          throws InterruptedException {  

3.      if (Thread.interrupted())  

4.          throw new InterruptedException();  

5.      Node node = addConditionWaiter();  

6.      int savedState = fullyRelease(node);  

7.      final long deadline = System.nanoTime() + nanosTimeout;  

8.      int interruptMode = 0;  

9.      while (!isOnSyncQueue(node)) {  

10.         if (nanosTimeout <= 0L) {  

11.             transferAfterCancelledWait(node);  

12.             break;  

13.         }  

14.         if (nanosTimeout >= spinForTimeoutThreshold)  

15.             LockSupport.parkNanos(this, nanosTimeout);  

16.         if ((interruptMode = checkInterruptWhileWaiting(node)) != 0)  

17.             break;  

18.         nanosTimeout = deadline - System.nanoTime();  

19.     }  

20.     if (acquireQueued(node, savedState) && interruptMode != THROW_IE)  

21.         interruptMode = REINTERRUPT;  

22.     if (node.nextWaiter != null)  

23.         unlinkCancelledWaiters();  

24.     if (interruptMode != 0)  

25.         reportInterruptAfterWait(interruptMode);  

26.     return deadline - System.nanoTime();  

27. }  
```



##### **（3）awaitUninterruptibly()**

之前看await()的源码我们知道它是会对interrupted的情况做出回应，也就是interrupted唤醒线程后，会判断throwException还是reInterrupted。

这里awaitUninterruptibly方法顾名思义**不会对interrupted做出回应，并且interrupted后会重新park**

```
1.  public final void awaitUninterruptibly() {  

2.      Node node = addConditionWaiter();  

3.      int savedState = fullyRelease(node);  

4.      boolean interrupted = false;  

5.      while (!isOnSyncQueue(node)) {  

6.          LockSupport.park(this); 

7.  //这里只是记录一下中断状态，然后重新循环进入park 

8.          if (Thread.interrupted())  

9.              interrupted = true;  

10.     }  

11.     if (acquireQueued(node, savedState) || interrupted)  

12.         selfInterrupt();  

13. }  
```



##### **（4）signal()**

通过上面await的源码我们知道线程被唤醒后会将它的节点从条件队列放到同步队列中去竞争锁的，所以带着这个目的来看signal方法

```
1.  public final void signal() {  

2.      if (!isHeldExclusively())  

3.          throw new IllegalMonitorStateException();  

4.      Node first = firstWaiter;  

5.      if (first != null)  

6.          doSignal(first);  

7.  }  

8.  private void doSignal(Node first) {  

9.      do {  

10.         if ( (firstWaiter = first.nextWaiter) == null)  

11.             lastWaiter = null;  

12.         first.nextWaiter = null;  //这里已经将节点的nextWaiter置为空

13.     } while (!transferForSignal(first) &&  

14.              (first = firstWaiter) != null);  

15. }  
```

在指定ConditionObject的条件队列中唤醒firstWaiter，也就是**修改waitstatus并加入同步队列**；如果唤醒失败就唤醒nextWaiter，以此类推，**所以说signal唤醒实际上不是随机的**，只是加入条件队列的节点顺序可能不一样。



核心唤醒方法transferForSignal

```
1.  final boolean transferForSignal(Node node) {  

2.      if (!compareAndSetWaitStatus(node, Node.CONDITION, 0))  

3.          return false;  

4.      Node p = enq(node);  

5.      int ws = p.waitStatus;  

6.      if (ws > 0 || !compareAndSetWaitStatus(p, ws, Node.SIGNAL))  

7.          LockSupport.unpark(node.thread);  

8.      return true;  

9.  }  
```



##### **（5）signalAll()**

唤醒指定ConditionObject条件队列中的所有等待节点，也就是遍历节点依次唤醒

核心方法如下

```
1.  private void doSignalAll(Node first) {  

2.      lastWaiter = firstWaiter = null;  

3.      do {  //遍历唤醒

4.          Node next = first.nextWaiter;  

5.          first.nextWaiter = null;  

6.          transferForSignal(first);  

7.          first = next;  

8.      } while (first != null);  

9.  }  
```



在await和signal之前都会判断一下当前线程是不是owner（调用方法isHeldExclusively()），跟wait/notify之前必须要拿到对象监视器一样。

**signal只是将节点从条件队列放到等待队列**，还要等待unlock的时候获取锁（unlock的时候会unpark同步队列中的第二个节点）。



这里思考过signal会不会将别的CondionObject条件队列节点放到同步队列中（错误唤醒），然后看到了ConditionObject对象中的两个变量

```
1.  /** First node of condition queue. */  

2.  private transient Node firstWaiter;  

3.  /** Last node of condition queue. */  

4.  private transient Node lastWaiter;  
```

当我们调用condition.await的时候，就是在这个ConditionObject中构建一条单向队列，使用firstWaiter和lastWaiter来记录，所以说**每一个ConditionObject对象单独维护一条单向条件队列**，所以也就不会冲突了。



#### **4、基于AQS的开源框架**

以 **ReentrantLock** 为例，state 初始化为 0，表示未锁定状态。A 线程 lock()时，会调用 tryAcquire()独占该锁并将 state+1。此后，其他线程再 tryAcquire()时就会失败，直到 A 线程 unlock()到 state=0（即释放锁）为止，其它线程才有机会获取该锁。当然，释放锁之前，A 线程自己是可以重复获取此锁的（state 会累加），这就是可重入的概念。但要注意，获取多少次就要释放多么次，这样才能保证 state 是能回到零态的。



**CountDownLatch**是共享锁的一种实现,它默认构造 AQS 的 state 值为 count。当线程使用countDown方法时,其实使用了tryReleaseShared方法以CAS的操作来减少state,直至state为0就代表所有的线程都调用了countDown方法。当调用await方法的时候，如果state不为0，就代表仍然有线程没有调用countDown方法，那么就把已经调用过countDown的线程都放入阻塞队列Park,并自旋CAS判断state == 0，直至最后一个线程调用了countDown，使得state == 0，于是阻塞的线程便判断成功，全部往下执行。



countDownLatch的一些经典使用场景

1）某一线程在开始运行前等待 n 个线程执行完毕。将 CountDownLatch 的计数器初始化为 n ：new CountDownLatch(n)，每当一个任务线程执行完毕，就将计数器减 1 countdownlatch.countDown()，当计数器的值变为 0 时，在CountDownLatch上 await() 的线程就会被唤醒。一个典型应用场景就是启动一个服务时，主线程需要等待多个组件加载完毕，之后再继续执行。

2）实现多个线程开始执行任务的最大并行性。注意是并行性，不是并发，强调的是多个线程在某一时刻同时开始执行。类似于赛跑，将多个线程放到起点，等待发令枪响，然后同时开跑。做法是初始化一个共享的 CountDownLatch 对象，将其计数器初始化为 1 ：new CountDownLatch(1)，多个线程在开始执行任务前首先 coundownlatch.await()，当主线程调用 countDown() 时，计数器变为 0，多个线程同时被唤醒。



**Semaphore**与CountDownLatch一样，也是共享锁的一种实现。它默认构造AQS的state为permits。当执行任务的线程数量超出permits,那么多余的线程将会被放入阻塞队列Park,并自旋判断state是否大于0。只有当state大于0的时候，阻塞的线程才能继续执行,此时先前执行任务的线程继续执行release方法，release方法使得state的变量会加1，那么自旋的线程便会判断成功。 如此，每次只有最多不超过permits数量的线程能自旋成功，便限制了执行任务线程的数量。



**CyclicBarrier** 和 CountDownLatch 非常类似，它也可以实现线程间的技术等待，CyclicBarrier 内部通过一个 count 变量作为计数器，cout 的初始值为 parties 属性的初始化值，每当一个线程到了栅栏这里了，那么就将计数器减一。如果 count 值为 0 了，表示这是这一代最后一个线程到达栅栏，就尝试执行我们构造方法中输入的任务。



CyclicBarrier 的经典使用案例有：

1）CyclicBarrier 可以用于多线程计算数据，最后合并计算结果的应用场景。比如我们用一个 Excel 保存了用户所有银行流水，每个 Sheet 保存一个帐户近一年的每笔银行流水，现在需要统计用户的日均银行流水，先用多线程处理每个 sheet 里的银行流水，都执行完之后，得到每个 sheet 的日均银行流水，最后，再用 barrierAction 用这些线程的计算结果，计算出整个 Excel 的日均银行流水。

CountDownLatch的实现是基于AQS的，而CycliBarrier是基于 ReentrantLock(ReentrantLock也属于AQS同步器)和 Condition 的。

CountDownLatch 是计数器，线程完成一个记录一个，只不过计数不是递增而是递减，而 CyclicBarrier 更像是一个阀门，需要所有线程都到达，阀门才能打开，然后继续执行。



#### **5、总结**

（1）LockSupport的park和unpark底层是基于jvm本地方法的，AQS实现阻塞和解除阻塞是基于LockSupport。



（2）AQS的实质是两种队列，一条双向同步队列，一条或多条单向条件队列

1）线程在获取不到lock之后会进入同步队列，找一个安全的位置（前置节点的waitstatus是SIGNAL，保证前置节点结束后会唤醒后置节点）将自己阻塞，等待唤醒后去获取锁。

2）线程在被await后会放弃lock并进入等待队列，在清理一次CANCELLED节点后将自己阻塞，等待唤醒后加入同步队列去获取锁（会对中断做出回应）。



（3）只有同步队列中的第二个节点才有资格去获取锁。



（4）公平锁和非公平锁的区别就是非公平锁每个线程都可以先直接尝试修改state的值（获取锁），然后在失败的情况下才会加入同步队列等待；公平锁就是要老老实实的在同步队列中排队。



（5）AQS只是一个框架，提供了很多方法给其他类重写从而实现不同的功能，如ReentrantLock实现了独占锁，Semaphore和CountDownLatch实现了共享锁，主要重写的逻辑和方法就是获取锁和释放锁。