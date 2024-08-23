手写Rpc通信框架上
2024-08-22
记录一次手写Rpc通信框架的上半部分
06.jpg
造轮子系列
huizhang43

这是一节手动造轮子系列

先讲一下基本的设计思路



参考rpc通信框架的经典dubbo，dubbo的简易架构如下



![img](http://pcc.huitogo.club/c518b5bada3cdf5f11f7b0e58026b443)



基本业内rpc框架需要考虑到的要素和配置dubbo都已经实现了，当然我们今天不是造一个dubbo，而是仿照dubbo的理念自己造一个轮子

我们的架构长什么样呢？



![img](http://pcc.huitogo.club/92505f81dff143477d5480ef87fc4bd2)



就是这个小巧的样子。

作为一个rpc框架应该具备哪些功能呢？



![img](http://pcc.huitogo.club/6983e64ac0fd58db8ff8705c3bcb618e)



我们仿照rpc框架的要求，实现的框架如下



![img](http://pcc.huitogo.club/a9f859660243433c06dad0067dfdffab)



接下来讲解实现的内容就是上图中介绍的功能



#### **1、编码思路**



首先是三个重要组件的任务



##### **1）消费端**



消费端需要将自己的服务（包括服务名和调用地址）暴露出去，也就是上传到注册中心

消费端需要处理服务端的连接请求和调用请求，我们还加上了心跳包处理

消费端需要及时断开无用连接，并对有效客户端保持长连接



##### **2）客户端**

客户端需要去注册中心拿到自己需要调用的服务地址，我们加上了负载均衡

客户端需要连接服务端并对服务端发起通信

客户端需要处理服务端响应结果作为自己的调用返回值



##### **3）注册中心**

注册中心的任务就是保存和提供服务地址



编码过程思路如下



```
1、zk Registry and discovery （loadBalance）

 

2、service Provider (expose for use) and service definition

 

3、refer dubbo SPI design for extension

 

4、netty server or socket server for receive requestMessage

 

netty : encode + decode + messageHandler

encode/decode：serializer + compress

 

5、netty client or socket client for send requestMessage

 

6、producer and consumer in spring lifestyle with SpringBeanPostProcessor

 

the service provided by producer which was annotated by @RpcService will be registered  to 
registration center

 

the field annotated by @RpcReference in consumer will create proxy object to be replaced into the field and it`s method will be invoked by proxy object 

 

7、scan the packages and find the class which was annotated by @RpcService and the detected packages was assigned by user with @RpcScan

 

8、create client and server to test this rpc framework
```



下面实现细节就是根据这些思路编码的



#### **2、实现细节**



##### **（1）注册中心**



先从简单的注册中心交互开始编码

本着抽象的原则，定义注册服务和查找服务的接口



```
1. @SPI 

2. public interface ServiceRegistry { 

3.  

4.   void registerService(String rpcServiceName, InetSocketAddress inetSocketAddress); 

5. } 

6.  

7. @SPI 

8. public interface ServiceDiscovery { 

9.  

10.   InetSocketAddress lookupService(String rpcServiceName); 

11. } 
```



这里@SPI代表着我们使用SPI来扩展这些服务的

我们注册中心采用zookeeper，所以基于zk的实现



ZkServiceRegistry：zk服务注册



```
1. public class ZkServiceRegistry implements ServiceRegistry { 

2.   @Override 

3.   public void registerService(String rpcServiceName, InetSocketAddress inetSocketAddress) { 

4.     String serviceNodePath = CuratorUtils.ZK_REGISTER_ROOT_PATH + "/" + rpcServiceName + inetSocketAddress.toString(); 

5.  

6.     CuratorFramework zkClient = CuratorUtils.getZkClient(); 

7.  

8.     CuratorUtils.createPersistentNode(zkClient, serviceNodePath); 

9.   } 

10. } 
```



ZkServiceDiscovery：zk服务发现



```
1. @Slf4j 

2. public class ZkServiceDiscovery implements ServiceDiscovery { 

4.   private LoadBalance loadBalance; 

6.   public ZkServiceDiscovery() { 

7.     // default loadBalance 

8.     this.loadBalance = new RandomLoadBalance(); 

9.   } 

10.  

11.   public ZkServiceDiscovery(LoadBalance loadBalance) { 

12.     this.loadBalance = loadBalance; 

13.   } 

14.  

15.   @Override 

16.   public InetSocketAddress lookupService(String rpcServiceName) { 

18.     CuratorFramework zkClient = CuratorUtils.getZkClient(); 

19.     List<String> serviceUrlList = CuratorUtils.getChildrenNodes(zkClient, rpcServiceName); 

20.  

21.     if (serviceUrlList.size() == 0) { 

22.       throw new RpcException(RpcErrorMessageEnum.SERVICE_CAN_NOT_BE_FOUND, rpcServiceName); 

23.     } 

24.     // load balancing 

25.     String targetServiceUrl = loadBalance.selectServiceAddress(serviceUrlList); 

26.  

27.     log.info("Successfully found the service address:[{}]", targetServiceUrl); 

28.     String[] socketAddressArray = targetServiceUrl.split(":"); 

29.  

30.     String host = socketAddressArray[0]; 

31.     int port = Integer.parseInt(socketAddressArray[1]); 

32.  

33.     return new InetSocketAddress(host, port); 

34.   } 

35. } 
```



这里有一个**zk的第三方工具包**Curator的封装类CuratorUtils

主要提供创建节点和查找节点的任务



这里服务发现的时候我们添加了**负载均衡**，如果服务提供者很多的话会根据负载均衡策略访问其中一个



LoadBalance接口和随机策略的实现类



```
1. public interface LoadBalance { 

3.   String selectServiceAddress(List<String> serviceAddresses); 

4. } 

5.  

6. public abstract class AbstractLoadBalance implements LoadBalance { 

8.   @Override 

9.   public String selectServiceAddress(List<String> serviceAddresses) { 

10.     if (serviceAddresses == null || serviceAddresses.size() == 0) { 

11.       return null; 

12.     } 

13.  

14.     if (serviceAddresses.size() == 1) { 

15.       return serviceAddresses.get(0); 

16.     } 

17.     return doSelect(serviceAddresses); 

18.   } 

19.  

20.   public abstract String doSelect(List<String> serviceAddresses); 

21. } 

22.  

23. public class RandomLoadBalance extends AbstractLoadBalance { 

24.  

25.   @Override 

26.   public String doSelect(List<String> serviceAddresses) { 

27.     Random random = new Random(); 

28.     return serviceAddresses.get(random.nextInt(serviceAddresses.size())); 

29.   } 

30. } 
```



这里采用模板模式将负载策略的公有特性提取出来



刚刚讲到了扩展ServiceDiscovery和ServiceRegistry采用SPI的设计理念，那这个**SPI怎么用**？



在resources/META-INF/目录下新建配置文件（类似Properties键值对文件），内容如下



```
1. zk=com.zhanghui.registry.zk.ZkServiceDiscovery 
```



然后借助ExtensionLoader工具类，当然这个工具类是从dubbo上抄的

在使用的时候不需要new我们的ServiceDiscovery实现类，而是



```
1. ServiceRegistry serviceRegistry = ExtensionLoader.getExtensionLoader(ServiceRegistry.class).getExtension("zk"); 
```



现在我们已经基于zk实现服务的注册和发现，而且基于SPI我们可以开发出更多的扩展功能，并且可以动态加载这些扩展类，但是我们还需要封装一下给开发人员使用



定义ServiceProvider接口提供服务的发布



```
1. public interface ServiceProvider { 

2.  

3.   void addService(Object service, Class<?> serviceClass, RpcServiceProperties rpcServiceProperties); 

4.  

5.   Object getService(RpcServiceProperties rpcServiceProperties); 

6.  

7.   void publishService(Object service, RpcServiceProperties rpcServiceProperties); 

8.  

9.   void publishService(Object service); 

10. } 
```



ServiceProvider的实现类ServiceProviderImpl



```
1. @Slf4j 

2. public class ServiceProviderImpl implements ServiceProvider { 

3.  

4.   private final Map<String, Object> serviceMap; 

5.  

6.   private final Set<String> registeredService; 

7.  

8.   private final ServiceRegistry serviceRegistry; 

9.  

10.   public ServiceProviderImpl() { 

11.     this.serviceMap = new ConcurrentHashMap<>(); 

12.     registeredService = ConcurrentHashMap.newKeySet(); 

13.  

14.     serviceRegistry = ExtensionLoader.getExtensionLoader(ServiceRegistry.class).getExtension("zk"); 

15.   } 

16.  

17.   @Override 

18.   public void addService(Object service, Class<?> serviceClass, RpcServiceProperties rpcServiceProperties) { 

19.     String rpcServiceName = rpcServiceProperties.toRpcServiceName(); 

20.     if (registeredService.contains(rpcServiceName)) { 

21.       return; 

22.     } 

23.     registeredService.add(rpcServiceName); 

24.     serviceMap.put(rpcServiceName, service); 

25.     log.info("Add service: {} and interfaces:{}", rpcServiceName, service.getClass().getInterfaces()); 

26.   } 

27.  

28.   @Override 

29.   public Object getService(RpcServiceProperties rpcServiceProperties) { 

30.     Object service = serviceMap.get(rpcServiceProperties.toRpcServiceName()); 

31.     if (null == service) { 

32.       throw new RpcException(RpcErrorMessageEnum.SERVICE_CAN_NOT_BE_FOUND); 

33.     } 

34.     return service; 

35.   } 

36.  

37.   @Override 

38.   public void publishService(Object service) { 

39.     this.publishService(service, RpcServiceProperties.builder().group("").version("").build()); 

40.   } 

41.  

42.   @Override 

43.   public void publishService(Object service, RpcServiceProperties rpcServiceProperties) { 

44.     try { 

45.       String host = InetAddress.getLocalHost().getHostAddress(); 

46.       Class<?> serviceRelatedInterface = service.getClass().getInterfaces()[0]; 

47.  

48.       String serviceName = serviceRelatedInterface.getCanonicalName(); 

49.  

50.       rpcServiceProperties.setServiceName(serviceName); 

51.       this.addService(service, serviceRelatedInterface, rpcServiceProperties); 

52.  

53.       serviceRegistry.registerService(rpcServiceProperties.toRpcServiceName(), new InetSocketAddress(host, NettyServer.PORT)); 

54.  

55.     } catch (UnknownHostException e) { 

56.       log.error("occur exception when getHostAddress", e); 

57.     } 

58.   } 

59. } 
```



这里发布服务的时候还向本地缓存一份，减少调用zk的次数。



##### **（2）服务端**



服务端和客户端的交互的方式我们这里有两种，**netty**和**socket**



先来看一下**netty**



NettyServer：服务端启动



```
1. @Slf4j 

2. @Component 

3. public class NettyServer { 

4.  

5.   public static final int PORT = 9998; 

6.  

7.   private final ServiceProvider serviceProvider = SingletonFactory.getInstance(ServiceProviderImpl.class); 

8.  

9.   public void registerService(Object service, RpcServiceProperties rpcServiceProperties) { 

10.     serviceProvider.publishService(service, rpcServiceProperties); 

11.   } 

12.  

13.   @SneakyThrows 

14.   public void start() { 

15.  

16.     // clear all 

17.     CustomShutdownHook customShutdownHook = new CustomShutdownHook(); 

18.     customShutdownHook.clearAll(); 

19.  

20.     String host = InetAddress.getLocalHost().getHostAddress(); 

21.  

22.     EventLoopGroup bossGroup = new NioEventLoopGroup(1); 

23.     EventLoopGroup workerGroup = new NioEventLoopGroup(); 

24.  

25.     DefaultEventExecutorGroup eventExecutors = new DefaultEventExecutorGroup(RuntimeUtil.cpus(), ThreadPoolFactoryUtils.createThreadFactory("server-handler-group", false)); 

26.  

27.     ServerBootstrap serverBootstrap = new ServerBootstrap(); 

28.  

29.     try { 

30.       serverBootstrap.group(bossGroup, workerGroup) 

31.           .channel(NioServerSocketChannel.class) 

32.           // TCP默认开启了 Nagle 算法，该算法的作用是尽可能的发送大数据快，减少网络传输。TCP_NODELAY 参数的作用就是控制是否启用 Nagle 算法。 

33.           .childOption(ChannelOption.TCP_NODELAY, true) 

34.           // 是否开启长连接 

35.           .childOption(ChannelOption.SO_KEEPALIVE, true) 

36.           //表示系统用于临时存放已完成三次握手的请求的队列的最大长度,如果连接建立频繁，服务器处理创建新连接较慢，可以适当调大这个参数 

37.           .option(ChannelOption.SO_BACKLOG, 128) 

38.           .handler(new LoggingHandler(LogLevel.INFO)) 

39.           // 当客户端第一次进行请求的时候才会进行初始化 

40.           .childHandler(new ChannelInitializer<SocketChannel>() { 

41.             @Override 

42.             protected void initChannel(SocketChannel ch) { 

43.               ChannelPipeline p = ch.pipeline(); 

44.               // 30 秒之内没有收到客户端请求的话就关闭连接 

45.               p.addLast(new IdleStateHandler(30, 0, 0, TimeUnit.SECONDS)); 

46.               p.addLast(new RpcMessageEncoder()); 

47.               p.addLast(new RpcMessageDecoder()); 

48.               p.addLast(eventExecutors, new **ServerMessageHandler**()); 

49.             } 

50.           }); 

51.  

52.       // 绑定端口，同步等待绑定成功 

53.       ChannelFuture future = serverBootstrap.bind(host, PORT).sync(); 

54.  

55.       // 等待服务端监听端口关闭 

56.       future.channel().closeFuture().sync(); 

57.     } catch (InterruptedException e) { 

58.       log.error("occur exception when start server:", e); 

59.     } finally { 

60.       log.error("shutdown bossGroup and workerGroup"); 

61.       bossGroup.shutdownGracefully(); 

62.       workerGroup.shutdownGracefully(); 

63.       eventExecutors.shutdownGracefully(); 

64.     } 

65.   } 

66. } 
```



netty服务端监听9998等待客户端的连接和请求

这里定义了一个自定义的ShutdownHook，在Netty Server每次start之前clen一下



CustomShutdownHook代码如下



```
1. @Slf4j 

2. public class CustomShutdownHook { 

3.   private static final CustomShutdownHook CUSTOM_SHUTDOWN_HOOK = new CustomShutdownHook(); 

4.  

5.   public static CustomShutdownHook getCustomShutdownHook() { 

6.     return CUSTOM_SHUTDOWN_HOOK; 

7.   } 

8.  

9.   public void clearAll() { 

10.     log.info("addShutdownHook for clearAll"); 

11.     Runtime.getRuntime().addShutdownHook(new Thread(() -> { 

12.       CuratorUtils.clearRegistry(CuratorUtils.getZkClient()); 

13.       ThreadPoolFactoryUtils.shutDownAllThreadPool(); 

14.     })); 

15.   } 

16. } 
```



这个ShutdownHook的任务就是清除zk端的服务节点和关闭系统正在运行的线程池。

在客户端的请求到达之后会依次经过**IdleStateHandler**（空闲连接处理）、**RpcMessageEncoder** 和**RpcMessageDecoder**。



这里有个非常重要的概念，就是通信协议，也就是我们通常说的报文格式

这里我们自定义了报文的编码和解码方式RpcMessageEncoder和RpcMessageDecoder



首先说一下自定义的特殊报文格式



![img](http://pcc.huitogo.club/6e14dfd06d32638c6dc9fff6c60254ac)



这里4字节魔法数的意义就是防止出现非法报文段，做过滤使用的。



对于编码的核心代码



```
1. @Override 

2. protected void encode(ChannelHandlerContext ctx, RpcMessage rpcMessage, ByteBuf out) { 

3.   try { 

4.     out.writeBytes(RpcConstants.MAGIC_NUMBER); 

5.     out.writeByte(RpcConstants.VERSION); 

6.     // leave a place to write the value of full length 

7.     out.writerIndex(out.writerIndex() + 4); 

8.     byte messageType = rpcMessage.getMessageType(); 

9.     out.writeByte(messageType); 

10.     out.writeByte(rpcMessage.getCodec()); 

11.     out.writeByte(CompressTypeEnum.GZIP.getCode()); 

12.     out.writeInt(ATOMIC_INTEGER.getAndIncrement()); 

13.     // build full length 

14.     byte[] bodyBytes = null; 

15.     int fullLength = RpcConstants.HEAD_LENGTH; 

16.     // if messageType is not heartbeat message,fullLength = head length + body length 

17.     if (messageType != RpcConstants.HEARTBEAT_REQUEST_TYPE 

18.         && messageType != RpcConstants.HEARTBEAT_RESPONSE_TYPE) { 

19.       // serialize the object 

20.       String codecName = SerializationTypeEnum.getName(rpcMessage.getCodec()); 

21.       Serializer serializer = ExtensionLoader.getExtensionLoader(Serializer.class) 

22.           .getExtension(codecName); 

23.       bodyBytes = serializer.serialize(rpcMessage.getData()); 

24.       // compress the bytes 

25.       String compressName = CompressTypeEnum.getName(rpcMessage.getCompress()); 

26.       Compress compress = ExtensionLoader.getExtensionLoader(Compress.class) 

27.           .getExtension(compressName); 

28.       bodyBytes = compress.compress(bodyBytes); 

29.       fullLength += bodyBytes.length; 

30.     } 

31.  

32.     if (bodyBytes != null) { 

33.       out.writeBytes(bodyBytes); 

34.     } 

35.     int writeIndex = out.writerIndex(); 

36.     out.writerIndex(writeIndex - fullLength + RpcConstants.MAGIC_NUMBER.length + 1); 

37.     out.writeInt(fullLength); 

38.     out.writerIndex(writeIndex); 

39.   } catch (Exception e) { 

40.     log.error("Encode request error!", e); 

41.   } 

42.  

43. } 
```



对于解码的核心代码



```
1. private Object decodeFrame(ByteBuf in) { 

2.   // note: must read ByteBuf in order 

3.   // read the first 4 bit, which is the magic number, and compare 

4.   int len = RpcConstants.MAGIC_NUMBER.length; 

5.   byte[] tmp = new byte[len]; 

6.   in.readBytes(tmp); 

7.   for (int i = 0; i < len; i++) { 

8.     if (tmp[i] != RpcConstants.MAGIC_NUMBER[i]) { 

9.       throw new IllegalArgumentException("Unknown magic code: " + Arrays.toString(tmp)); 

10.     } 

11.   } 

12.   // read the version and compare 

13.   byte version = in.readByte(); 

14.   if ( version!= RpcConstants.VERSION) { 

15.     throw new RuntimeException("version isn't compatible" + version); 

16.   } 

17.   int fullLength = in.readInt(); 

18.   // build RpcMessage object 

19.   byte messageType = in.readByte(); 

20.   byte codecType = in.readByte(); 

21.   byte compressType = in.readByte(); 

22.   int requestId = in.readInt(); 

23.   RpcMessage rpcMessage = RpcMessage.builder() 

24.       .codec(codecType) 

25.       .requestId(requestId) 

26.       .messageType(messageType).build(); 

27.   if (messageType == RpcConstants.HEARTBEAT_REQUEST_TYPE) { 

28.     rpcMessage.setData(RpcConstants.PING); 

29.   } else if (messageType == RpcConstants.HEARTBEAT_RESPONSE_TYPE) { 

30.     rpcMessage.setData(RpcConstants.PONG); 

31.   } else { 

32.     int bodyLength = fullLength - RpcConstants.HEAD_LENGTH; 

33.     if (bodyLength > 0) { 

34.       byte[] bs = new byte[bodyLength]; 

35.       in.readBytes(bs); 

36.       // decompress the bytes 

37.       String compressName = CompressTypeEnum.getName(compressType); 

38.       Compress compress = ExtensionLoader.getExtensionLoader(Compress.class) 

39.           .getExtension(compressName); 

40.       bs = compress.decompress(bs); 

41.       // deserialize the object 

42.       String codecName = SerializationTypeEnum.getName(rpcMessage.getCodec()); 

43.       Serializer serializer = ExtensionLoader.getExtensionLoader(Serializer.class) 

44.           .getExtension(codecName); 

45.       if (messageType == RpcConstants.REQUEST_TYPE) { 

46.         RpcRequest tmpValue = serializer.deserialize(bs, RpcRequest.class); 

47.         rpcMessage.setData(tmpValue); 

48.       } else { 

49.         RpcResponse tmpValue = serializer.deserialize(bs, RpcResponse.class); 

50.         rpcMessage.setData(tmpValue); 

51.       } 

52.     } 

53.   } 

54.   return rpcMessage; 

55.  

56. } 
```



我们这里对消息体采用的序列化方式是kyro，压缩方式是gzip

在经过编解码处理后，我们得到客户端的请求体RpcMessage，到我们的MessageHandler



ServerMessageHandler：消息处理类



```
1. @Slf4j 

2. public class ServerMessageHandler extends ChannelInboundHandlerAdapter { 

3.  

4.   private final RpcRequestHandler rpcRequestHandler; 

5.  

6.   public ServerMessageHandler() { 

7.     this.rpcRequestHandler = SingletonFactory.getInstance(RpcRequestHandler.class); 

8.   } 

9.  

10.   @Override 

11.   public void channelRead(ChannelHandlerContext ctx, Object msg) { 

12.     try { 

13.       if (msg instanceof RpcMessage) { 

14.         log.info("server receive msg: [{}] ", msg); 

15.         byte messageType = ((RpcMessage) msg).getMessageType(); 

16.         if (messageType == RpcConstants.HEARTBEAT_REQUEST_TYPE) { 

17.           RpcMessage rpcMessage = new RpcMessage(); 

18.           rpcMessage.setCodec(SerializationTypeEnum.KYRO.getCode()); 

19.           rpcMessage.setCompress(CompressTypeEnum.GZIP.getCode()); 

20.           rpcMessage.setMessageType(RpcConstants.HEARTBEAT_RESPONSE_TYPE); 

21.           rpcMessage.setData(RpcConstants.PONG); 

22.           ctx.writeAndFlush(rpcMessage).addListener(ChannelFutureListener.CLOSE_ON_FAILURE); 

23.         } else { 

24.           RpcRequest rpcRequest = (RpcRequest) ((RpcMessage) msg).getData(); 

25.           // Execute the target method (the method the client needs to execute) and return the method result 

26.           Object result = rpcRequestHandler.handle(rpcRequest); 

27.           log.info(String.format("server get result: %s", result.toString())); 

28.           if (ctx.channel().isActive() && ctx.channel().isWritable()) { 

29.             RpcResponse<Object> rpcResponse = RpcResponse.success(result, rpcRequest.getRequestId()); 

30.             RpcMessage rpcMessage = new RpcMessage(); 

31.             rpcMessage.setCodec(SerializationTypeEnum.KYRO.getCode()); 

32.             rpcMessage.setCompress(CompressTypeEnum.GZIP.getCode()); 

33.             rpcMessage.setMessageType(RpcConstants.RESPONSE_TYPE); 

34.             rpcMessage.setData(rpcResponse); 

35.             ctx.writeAndFlush(rpcMessage).addListener(ChannelFutureListener.CLOSE_ON_FAILURE); 

36.           } else { 

37.             RpcResponse<Object> rpcResponse = RpcResponse.fail(RpcResponseCodeEnum.FAIL); 

38.             RpcMessage rpcMessage = new RpcMessage(); 

39.             rpcMessage.setCodec(SerializationTypeEnum.KYRO.getCode()); 

40.             rpcMessage.setCompress(CompressTypeEnum.GZIP.getCode()); 

41.             rpcMessage.setMessageType(RpcConstants.RESPONSE_TYPE); 

42.             rpcMessage.setData(rpcResponse); 

43.             ctx.writeAndFlush(rpcMessage).addListener(ChannelFutureListener.CLOSE_ON_FAILURE); 

44.             log.error("not writable now, message dropped"); 

45.           } 

46.         } 

47.       } 

48.  

49.     } finally { 

50.       //Ensure that ByteBuf is released, otherwise there may be memory leaks 

51.       ReferenceCountUtil.release(msg); 

52.     } 

53.   } 
```



服务端消息处理器只处理客户端心跳消息和客户端的报文请求

这里将报文请求核心处理内容提取到RpcRequestHandler中



```
1. @Slf4j 

2. public class RpcRequestHandler { 

3.  

4.   private final ServiceProvider serviceProvider; 

5.  

6.   public RpcRequestHandler() { 

7.     serviceProvider = SingletonFactory.getInstance(ServiceProviderImpl.class); 

8.   } 

9.  

10.   /** 

11.   * Processing rpcRequest: call the corresponding method, and then return the method 

12.   */ 

13.   public Object handle(RpcRequest rpcRequest) { 

14.     Object service = serviceProvider.getService(rpcRequest.toRpcProperties()); 

15.     return invokeTargetMethod(rpcRequest, service); 

16.   } 

17.  

18.   /** 

19.   * get method execution results 

20.   * 

21.   * @param rpcRequest client request 

22.   * @param service  service object 

23.   * @return the result of the target method execution 

24.   */ 

25.   private Object invokeTargetMethod(RpcRequest rpcRequest, Object service) { 

26.     Object result; 

27.     try { 

28.       Method method = service.getClass().getMethod(rpcRequest.getMethodName(), rpcRequest.getParamTypes()); 

29.  

30.       result = method.invoke(service, rpcRequest.getParameters()); 

31.       log.info("service:[{}] successful invoke method:[{}]", rpcRequest.getInterfaceName(), rpcRequest.getMethodName()); 

32.     } catch (NoSuchMethodException | IllegalAccessException | InvocationTargetException e) { 

33.       throw new RpcException(e.getMessage(), e); 

34.     } 

35.     return result; 

36.   } 

37. } 
```



处理过程就是通过请求报文中的类名、方法名和参数值使用反射调用获取结果

然后NettyServer将返回结果封装成RpcMessage后writeAndFlush到客户端



看完netty的服务端后再来看一下基于socket的服务端



```
1. @Slf4j 

2. public class SocketServer { 

3.  

4.   private final ExecutorService threadPool; 

5.   private final ServiceProvider serviceProvider; 

6.  

7.   public SocketServer() { 

8.     serviceProvider = SingletonFactory.getInstance(ServiceProviderImpl.class); 

9.     threadPool = ThreadPoolFactoryUtils.createCustomThreadPoolIfAbsent("rpc-socket-server-pool"); 

10.   } 

11.  

12.   public void registerService(Object service) { 

13.     serviceProvider.publishService(service); 

14.   } 

15.  

16.   public void registerService(Object service, RpcServiceProperties rpcServiceProperties) { 

17.     serviceProvider.publishService(service, rpcServiceProperties); 

18.   } 

19.  

20.   public void start() { 

21.     try (ServerSocket serverSocket = new ServerSocket()) { 

22.       String host = InetAddress.getLocalHost().getHostAddress(); 

23.       serverSocket.bind(new InetSocketAddress(host, NettyServer.PORT)); 

24.       CustomShutdownHook.getCustomShutdownHook().clearAll(); 

25.       Socket socket; 

26.       while ((socket = serverSocket.accept()) != null) { 

27.         log.info("client connected [{}]", socket.getInetAddress()); 

28.         threadPool.execute(new SocketRequestHanlderRunnable(socket)); 

29.       } 

30.       threadPool.shutdown(); 

31.     } catch (IOException ex) { 

32.       log.error("occur Exception, ", ex); 

33.     } 

34.   } 

35. } 
```



socket的服务端在accept等待客户端连接

在有连接请求过来的时候使用线程池处理请求，处理过程如下



```
1. @Slf4j 

2. public class SocketRequestHanlderRunnable implements Runnable { 

3.  

4.   private final Socket socket; 

5.   private final RpcRequestHandler rpcRequestHandler; 

6.  

7.   public SocketRequestHanlderRunnable(Socket socket) { 

8.     this.socket = socket; 

9.     rpcRequestHandler = SingletonFactory.getInstance(RpcRequestHandler.class); 

10.   } 

11.  

12.   @Override 

13.   public void run() { 

14.     log.info("server handle message from client by thread: [{}]", Thread.currentThread().getName()); 

15.     try (ObjectInputStream inputStream = new ObjectInputStream(socket.getInputStream()); 

16.       ObjectOutputStream outputStream = new ObjectOutputStream(socket.getOutputStream())) { 

17.  

18.       RpcRequest rpcRequest = (RpcRequest) inputStream.readObject(); 

19.       Object result = rpcRequestHandler.handle(rpcRequest); 

20.       outputStream.writeObject(RpcResponse.success(result, rpcRequest.getRequestId())); 

21.       outputStream.flush(); 

22.     } catch (IOException | ClassNotFoundException ex) { 

23.       log.error("occur exception:", ex); 

24.     } 

25.   } 

26. } 
```



借助ObjectStream读写消息体，核心处理还是RpcRequestHandler