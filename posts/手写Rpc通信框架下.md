手写Rpc通信框架下
2024-08-22
记录一次手写Rpc通信框架的下半部分
06.jpg
造轮子系列
huizhang43

#### **1. 消费端**



对于消费端的发送请求也是分netty client和socket client分别处理了



先看下netty client

Netty client：连接Netty Server 获取Channel



```
1. @Slf4j 

2. public class NettyClient { 

3.  

4.   private final Bootstrap bootstrap; 

5.  

6.   private final EventLoopGroup workersGroup; 

7.  

8.   // initialize resources such as EventLoopGroup, Bootstrap 

9.   public NettyClient() { 

10.  

11.     workersGroup = new NioEventLoopGroup(); 

12.  

13.     bootstrap = new Bootstrap(); 

14.     bootstrap.group(workersGroup) 

15.         .channel(NioSocketChannel.class) 

16.         .handler(new LoggingHandler(LogLevel.INFO)) 

17.         // The timeout period of the connection. 

18.         // If this time is exceeded or the connection cannot be established, the connection fails. 

19.         .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000) 

20.         .handler(new ChannelInitializer<SocketChannel>() { 

21.           @Override 

22.           protected void initChannel(SocketChannel ch) throws Exception { 

23.             ChannelPipeline pipeline = ch.pipeline(); 

24.             // If no data is sent to the server within 15 seconds, a heartbeat request is sent 

25.             pipeline.addLast(new IdleStateHandler(0, 15, 0, TimeUnit.SECONDS)); 

26.             pipeline.addLast(new RpcMessageEncoder()); 

27.             pipeline.addLast(new RpcMessageDecoder()); 

28.             pipeline.addLast(new ClientMessageHandler()); 

29.           } 

30.         }); 

31.   } 

32.  

33.   /** 

34.   * connect server and get the channel ,so that you can send rpc message to server 

35.   * 

36.   * @param socketAddress server address 

37.   * @return the channel 

38.   */ 

39.   @SneakyThrows 

40.   public Channel doConnect(InetSocketAddress socketAddress) { 

41.  

42.     CompletableFuture<Channel> completableFuture = new CompletableFuture<>(); 

43.  

44.     bootstrap.connect(socketAddress).addListener((ChannelFutureListener) future -> { 

45.       if (future.isSuccess()) { 

46.         log.info("The client has connected [{}] successful", socketAddress.toString()); 

47.         completableFuture.complete(future.channel()); 

48.       } else { 

49.         completableFuture.completeExceptionally(future.cause()); 

50.         throw new RpcException(RpcErrorMessageEnum.CLIENT_CONNECT_SERVER_FAILURE, "connect " + socketAddress.toString() + " failure"); 

51.       } 

52.     }); 

53.     return completableFuture.get(); 

54.   } 

55.  

56.   public void close() { 

57.     workersGroup.shutdownGracefully(); 

58.   } 

59. } 
```



Netty client 对于响应消息的处理也是经过IdleStateHandler（空闲连接处理类）、RpcMessageEncoder和RpcMessageDecoder

对于ClientMessageHandler我们待会儿再看

通过Netty client连接到Netty server获取到Channel后，我们可以基于Channel发送报文和心跳包



对于消费端发送请求，这里抽象出ClientTransport接口做扩展用



```
1. @SPI 

2. public interface ClientTransport { 

3.  

4.   Object sendRpcRequest(RpcRequest rpcRequest); 

5. } 
```



对于Netty的实现NettyClientTransport



```
1. @Slf4j 

2. public class NettyClientTransport implements ClientTransport { 

3.  

4.   private final ServiceDiscovery serviceDiscovery; 

5.   private final ChannelProvider channelProvider; 

6.   private final UnProcessedRequest unProcessedRequest; 

7.  

8.   public NettyClientTransport() { 

9.     serviceDiscovery = ExtensionLoader.getExtensionLoader(ServiceDiscovery.class).getExtension("zk"); 

10.     channelProvider = SingletonFactory.getInstance(ChannelProvider.class); 

11.     unProcessedRequest = SingletonFactory.getInstance(UnProcessedRequest.class); 

12.   } 

13.  

14.   @Override 

15.   public CompletableFuture<RpcResponse> sendRpcRequest(RpcRequest rpcRequest) { 

16.  

17.     CompletableFuture<RpcResponse> completableFuture = new CompletableFuture<>(); 

18.  

19.     unProcessedRequest.put(rpcRequest.getRequestId(),completableFuture); 

20.  

21.     String rpcServiceName = rpcRequest.toRpcProperties().toRpcServiceName(); 

22.  

23.     InetSocketAddress inetAddress = serviceDiscovery.lookupService(rpcServiceName); 

24.  

25.     Channel channel = channelProvider.get(inetAddress); 

26.  

27.     if (channel != null && channel.isActive()) { 

28.       RpcMessage rpcMessage = new RpcMessage(); 

29.       rpcMessage.setCodec(SerializationTypeEnum.KYRO.getCode()); 

30.       rpcMessage.setCompress(CompressTypeEnum.GZIP.getCode()); 

31.       rpcMessage.setData(rpcRequest); 

32.       rpcMessage.setMessageType(RpcConstants.REQUEST_TYPE); 

33.  

34.       channel.writeAndFlush(rpcMessage).addListener((ChannelFutureListener) future -> { 

35.         if (future.isSuccess()) { 

36.           log.info("client send message: [{}]", rpcMessage); 

37.         } else { 

38.           future.channel().close(); 

39.           completableFuture.completeExceptionally(future.cause()); 

40.           log.error("Send failed:", future.cause()); 

41.         } 

42.       }); 

43.     } else { 

44.       throw new RpcException(RpcErrorMessageEnum.CLIENT_CONNECT_SERVER_FAILURE); 

45.     } 

46.     return completableFuture; 

47.   } 

48. } 
```



这里需要注意的有三点



1）使用CompletableFuture做sendRpcRequest方法返回值的结果



对于netty在writeAndFlush后使用ChannelFutureListener只能监听请求发送情况，而不能获取sever端返回的内容，我们需要一个异步的同时支持多线程操作的容器



2）我们不能每次调用服务端都要doConnect一次，因为我们使用的是长连接



所以这里借助ChannelProvider来尝试获取我们的缓存Channel

ChannelProvider：从缓存中获取Channel，如果不存在或者Channel已失效则doConnect



```
1. @Slf4j 

2. public class ChannelProvider { 

3.  

4.   private final Map<String, Channel> channelMap; 

5.   private final NettyClient nettyClient; 

6.  

7.   public ChannelProvider() { 

8.     this.channelMap = new ConcurrentHashMap<>(); 

9.     this.nettyClient = SingletonFactory.getInstance(NettyClient.class); 

10.   } 

11.  

12.  

13.   public Channel get(InetSocketAddress inetSocketAddress) { 

14.  

15.     String key = inetSocketAddress.toString(); 

16.  

17.     //determine whether there is a connection in cache map 

18.     if (channelMap.containsKey(key)) { 

19.  

20.       Channel cacheChannel = channelMap.get(key); 

21.       // determine the cache connection is available 

22.       if (cacheChannel != null && cacheChannel.isActive()) { 

23.         return cacheChannel; 

24.       } else { 

25.         channelMap.remove(key); 

26.       } 

27.     } 

28.  

29.     // return new connection 

30.     Channel newChannel = nettyClient.doConnect(inetSocketAddress); 

31.  

32.     channelMap.put(key, newChannel); 

33.  

34.     return newChannel; 

35.   } 

36.  

37.   public void remove(InetSocketAddress inetSocketAddress) { 

38.     String key = inetSocketAddress.toString(); 

39.  

40.     channelMap.remove(key); 

41.  

42.     log.info("has remove [{}] connection from cache", key); 

43.   } 

44. } 
```



可以看到核心原理是缓存了一个Map



3）使用UnProcessedRequest来异步填充CompletableFuture的value



怎么填充呢？借助RpcMessage中的唯一requestId

先来看下UnProcessedRequest类



```
1. public class UnProcessedRequest { 

2.  

3.   private static final Map<String, CompletableFuture<RpcResponse>> UNPROCESSED_RESPONSE_FUTURES = new ConcurrentHashMap<>(); 

4.  

5.   public void put(String requestId, CompletableFuture<RpcResponse> future) { 

6.     UNPROCESSED_RESPONSE_FUTURES.put(requestId, future); 

7.   } 

8.  

9.   public void complete(RpcResponse response) { 

10.     CompletableFuture future = UNPROCESSED_RESPONSE_FUTURES.remove(response.getRequestId()); 

11.  

12.     if (future != null) { 

13.       future.complete(response); 

14.     } else { 

15.       throw new IllegalStateException(); 

16.     } 

17.   } 

18. } 
```



里面只有一个Map，key是requestId，value是CompletableFuture



在sendRpcRequest的时候往Map里面填充key/value，那什么时候为里面的CompletableFuture填充值呢？



又回到了ClientMessageHandler，因为netty client只能接收netty server发送过来的报文来获取自己之前请求的响应结果



```
1. @Slf4j 

2. public class ClientMessageHandler extends ChannelInboundHandlerAdapter { 

3.  

4.   private final UnProcessedRequest unProcessedRequest; 

5.   private final ChannelProvider channelProvider; 

6.  

7.   public ClientMessageHandler() { 

8.     this.unProcessedRequest = SingletonFactory.getInstance(UnProcessedRequest.class); 

9.     this.channelProvider = SingletonFactory.getInstance(ChannelProvider.class); 

10.   } 

11.  

12.   @Override 

13.   public void channelRead(ChannelHandlerContext ctx, Object msg) { 

14.     try { 

15.       log.info("client receive msg: [{}]", msg); 

16.       if (msg instanceof RpcMessage) { 

17.         RpcMessage rpcMessage = (RpcMessage) msg; 

18.         if (rpcMessage.getMessageType() == RpcConstants.HEARTBEAT_RESPONSE_TYPE) { 

19.           log.info("heart [{}]", rpcMessage.getData()); 

20.         } else if (rpcMessage.getMessageType() == RpcConstants.RESPONSE_TYPE) { 

21.           RpcResponse response = (RpcResponse) rpcMessage.getData(); 

22.           unProcessedRequest.complete(response); 

23.         } 

24.       } 

25.     } finally { 

26.       ReferenceCountUtil.release(msg); 

27.     } 

28.   } 

29.  

30.   @Override 

31.   public void userEventTriggered(ChannelHandlerContext ctx, Object evt) throws Exception { 

32.  

33.     // send heartbeat package to server when client is in idle state (we set the time is 15 seconds) 

34.     if (evt instanceof IdleStateEvent) { 

35.       log.info("write idle happen [{}]", ctx.channel().remoteAddress()); 

36.  

37.       Channel channel = channelProvider.get((InetSocketAddress) ctx.channel().remoteAddress()); 

38.  

39.       RpcMessage rpcMessage = new RpcMessage(); 

40.       rpcMessage.setMessageType(RpcConstants.HEARTBEAT_REQUEST_TYPE); 

41.       rpcMessage.setCodec(SerializationTypeEnum.KYRO.getCode()); 

42.       rpcMessage.setCompress(CompressTypeEnum.GZIP.getCode()); 

43.       rpcMessage.setData(RpcConstants.PING); 

44.  

45.       channel.writeAndFlush(rpcMessage).addListener(ChannelFutureListener.CLOSE_ON_FAILURE); 

46.     } else { 

47.       super.userEventTriggered(ctx, evt); 

48.     } 

49.   } 

50.  

51.   @Override 

52.   public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) throws Exception { 

53.     log.error("client catch exception：", cause); 

54.     cause.printStackTrace(); 

55.     ctx.close(); 

56.   } 

57. } 
```



所以我们通过ClientMessageHandler 来为UnProcessedReqeust下面Map中指定requestId的CompletableFuture填充value。

这里可以看到在IdleStateEvent触发的时候消费端会主动向服务端发送心跳包，这就是我们心跳机制的实现了。



基于netty实现的client请求已经完成了



基于socket怎么实现呢？借助Socket就可以了



SocketClientTransport：基于Socket实现ClientTransport



```
1. public class SocketClientTransport implements ClientTransport { 

2.  

3.   private final ServiceDiscovery serviceDiscovery; 

4.  

5.   public SocketClientTransport() { 

6.     this.serviceDiscovery = ExtensionLoader.getExtensionLoader(ServiceDiscovery.class).getExtension("zk"); 

7.   } 

8.  

9.   @Override 

10.   public Object sendRpcRequest(RpcRequest rpcRequest) { 

11.     // build rpc service name by rpcRequest 

12.     String rpcServiceName = RpcServiceProperties.builder() 

13.         .serviceName(rpcRequest.getInterfaceName()) 

14.         .group(rpcRequest.getGroup()) 

15.         .version(rpcRequest.getVersion()) 

16.         .build().toRpcServiceName(); 

17.     InetSocketAddress socketAddress = serviceDiscovery.lookupService(rpcServiceName); 

18.     try (Socket socket = new Socket()) { 

19.       socket.connect(socketAddress); 

20.       ObjectOutputStream outputStream = new ObjectOutputStream(socket.getOutputStream()); 

21.       outputStream.writeObject(rpcRequest); 

22.       ObjectInputStream inputStream = new ObjectInputStream(socket.getInputStream()); 

23.       return inputStream.readObject(); 

24.  

25.     } catch (IOException | ClassNotFoundException ex) { 

26.       throw new RpcException("调用服务失败:", ex); 

27.     } 

28.   } 

29. } 
```



可以看到就是基于Socket端口传输RpcRequest对象



#### **2. 嵌入Spring**



这里嵌入Spring主要指使用注解的方式实现rpc的通信

正如dubbo中使用的



```
1. @Reference(check =false, timeout = 10000,version="0.0.1",group="AS_SSC_BE_SSCPLAT") 

2. com.dap.api.IService iService2; 

3.  

4. @Component 

5. @Service(version = "1.0.0",timeout = 10000,interfaceClass = RemoteUserService.class) 

6. public class RemoteUserServiceImpl implements RemoteUserService {} 
```



我们也定义两个注解RpcReference和RpcService，当然使用方式和dubbo是一样的



```
1. @Documented 

2. @Retention(RetentionPolicy.RUNTIME) 

3. @Target({ElementType.FIELD}) 

4. @Inherited 

5. public @interface RpcReference { 

6.  

7.   String version() default ""; 

8.  

9.   String group() default ""; 

10.  

11. } 

12.  

13. @Documented 

14. @Retention(RetentionPolicy.RUNTIME) 

15. @Target({ElementType.TYPE}) 

16. @Inherited 

17. public @interface RpcService { 

18.  

19.   String version() default ""; 

20.  

21.   String group() default ""; 

22.  

23. } 
```



@RpcService是注解在type上的，我们希望被@RpcService注释的bean在程序启动的时候就将自己的服务注册到zookeeper上

@RpcReference是注解在field上的，我们希望如果Bean中有field被@RpcReference注解了，那么我们将这个field的变量替换成我们指定的代理对象，让代理对象调用ClientTransport中的sendRpcRequest方法获取我们想要的结果



因此我们想到了Spring生命周期中的BeanPostProcessor



SpringBeanPostProcessor：处理被@RpcService或者@RpcReference注解的Bean或者Bean中的field



```
1. @Slf4j 

2. @Component 

3. public class SpringBeanPostProcessor implements BeanPostProcessor { 

4.  

5.   private final ServiceProvider serviceProvider; 

6.   private final ClientTransport clientTransport; 

7.  

8.   public SpringBeanPostProcessor() { 

9.     this.serviceProvider = SingletonFactory.getInstance(ServiceProviderImpl.class); 

10.     this.clientTransport = ExtensionLoader.getExtensionLoader(ClientTransport.class).getExtension("nettyClientTransport"); 

11.   } 

12.  

13.   @Override 

14.   public Object postProcessBeforeInitialization(Object bean, String beanName) { 

15.  

16.     // registry the service annotated by @RpcService 

17.     if (bean.getClass().isAnnotationPresent(RpcService.class)) { 

18.       log.info("[{}] is annotated with [{}]", bean.getClass().getName(), RpcService.class.getCanonicalName()); 

19.       RpcService rpcService = bean.getClass().getAnnotation(RpcService.class); 

20.       RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

21.           .version(rpcService.version()).group(rpcService.group()).build(); 

22.       serviceProvider.publishService(bean, rpcServiceProperties); 

23.     } 

24.     return bean; 

25.   } 

26.  

27.   @Override 

28.   public Object postProcessAfterInitialization(Object bean, String beanName) { 

29.     Class targetClass = bean.getClass(); 

30.  

31.     Field[] fields = targetClass.getDeclaredFields(); 

32.  

33.     for (Field field : fields) { 

34.  

35.       // check the field which was annotated by @RpcReference 

36.       RpcReference rpcReference = field.getAnnotation(RpcReference.class); 

37.       if (rpcReference != null) { 

38.         RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

39.             .version(rpcReference.version()).group(rpcReference.group()).build(); 

40.  

41.         // aim to create proxy object for the bean which was annotated by @RpcReference 

42.         RpcClientProxy rpcClientProxy = new RpcClientProxy(clientTransport, rpcServiceProperties); 

43.         Object serviceProxy = rpcClientProxy.getProxy(field.getType()); 

44.  

45.         // set the field accessible when it`s decorated by private 

46.         field.setAccessible(true); 

47.  

48.         try { 

49.           field.set(bean, serviceProxy); 

50.         } catch (IllegalAccessException e) { 

51.           throw new RpcException(e.getMessage(), e.getCause()); 

52.         } 

53.       } 

54.     } 

55.     return bean; 

56.   } 

57. } 
```



基本实现思路跟我们上述分析的一样，这里我们实现代理的方式使用jdk动态代理，反正调用的Service肯定是一个接口



RpcClientProxy：为被@RpcReference注解的field生成jdk动态代理对象



```
1. @Slf4j 

2. public class RpcClientProxy implements InvocationHandler { 

3.  

4.   private final RpcServiceProperties rpcServiceProperties; 

5.   private static final String INTERFACE_NAME = "interfaceName"; 

6.  

7.   /** 

8.   * Used to send requests to the server.And there are two implementations: socket and netty 

9.   */ 

10.   private final ClientTransport clientTransport; 

11.  

12.   public RpcClientProxy(ClientTransport clientTransport, RpcServiceProperties rpcServiceProperties) { 

13.     this.clientTransport = clientTransport; 

14.     if (rpcServiceProperties.getGroup() == null) { 

15.       rpcServiceProperties.setGroup(""); 

16.     } 

17.     if (rpcServiceProperties.getVersion() == null) { 

18.       rpcServiceProperties.setVersion(""); 

19.     } 

20.     this.rpcServiceProperties = rpcServiceProperties; 

21.   } 

22.  

23.  

24.   public RpcClientProxy(ClientTransport clientTransport) { 

25.     this.clientTransport = clientTransport; 

26.     this.rpcServiceProperties = RpcServiceProperties.builder().group("").version("").build(); 

27.   } 

28.  

29.   @SuppressWarnings("unchecked") 

30.   public <T> T getProxy(Class<T> clazz) { 

31.     return (T) Proxy.newProxyInstance(clazz.getClassLoader(), new Class<?>[]{clazz}, this); 

32.   } 

33.  

34.   /** 

35.   * This method is actually called when you use a proxy object to call a method. 

36.   * The proxy object is the object you get through the getProxy method. 

37.   */ 

38.   @SneakyThrows 

39.   @Override 

40.   public Object invoke(Object proxy, Method method, Object[] args) throws Throwable { 

41.     log.info("invoked method: [{}]", method.getName()); 

42.     RpcRequest rpcRequest = RpcRequest.builder().methodName(method.getName()) 

43.         .parameters(args) 

44.         .interfaceName(method.getDeclaringClass().getName()) 

45.         .paramTypes(method.getParameterTypes()) 

46.         .requestId(UUID.randomUUID().toString()) 

47.         .group(rpcServiceProperties.getGroup()) 

48.         .version(rpcServiceProperties.getVersion()).build(); 

49.  

50.     RpcResponse rpcResponse = null; 

51.  

52.     if (clientTransport instanceof NettyClientTransport) { 

53.       CompletableFuture<RpcResponse> completableFuture = ((NettyClientTransport) clientTransport).sendRpcRequest(rpcRequest); 

54.       rpcResponse = completableFuture.get(); 

55.     } else if (clientTransport instanceof SocketClientTransport) { 

56.       rpcResponse = (RpcResponse) clientTransport.sendRpcRequest(rpcRequest); 

57.     } 

58.     this.check(rpcResponse, rpcRequest); 

59.     return rpcResponse.getData(); 

60.   } 

61.  

62.   private void check(RpcResponse rpcResponse, RpcRequest rpcRequest) { 

63.     if (rpcResponse == null) { 

64.       throw new RpcException(RpcErrorMessageEnum.SERVICE_INVOCATION_FAILURE, INTERFACE_NAME + ":" + rpcRequest.getInterfaceName()); 

65.     } 

66.  

67.     if (!rpcRequest.getRequestId().equals(rpcResponse.getRequestId())) { 

68.       throw new RpcException(RpcErrorMessageEnum.REQUEST_NOT_MATCH_RESPONSE, INTERFACE_NAME + ":" + rpcRequest.getInterfaceName()); 

69.     } 

70.  

71.     if (rpcResponse.getCode() == null || !rpcResponse.getCode().equals(RpcResponseCodeEnum.SUCCESS.getCode())) { 

72.       throw new RpcException(RpcErrorMessageEnum.SERVICE_INVOCATION_FAILURE, INTERFACE_NAME + ":" + rpcRequest.getInterfaceName()); 

73.     } 

74.   } 

75. } 
```



因为我们这里对NettyClientTransport和SocketClientTransport两种方式的结果做了判断，所以代码稍微冗长了一定。

核心原理就是封装RpcRequest，调用ClientTranspor的sendRpcRequest方法



现在我们已经实现了刚刚分析的两个小目标，现在问题来了，怎么将@RpcService注解的类和我们rpc-framework-core中的Spring Bean放到用户的Spring上下文中

所以我们自定义扫描机制



先定义一个扫描注解



```
1. @Target({ElementType.TYPE, ElementType.METHOD}) 

2. @Retention(RetentionPolicy.RUNTIME) 

3. @Import(CustomScannerRegistrar.class) 

4. @Documented 

5. public @interface RpcScan { 

6.  

7.   String[] basePackage(); 

8.  

9. } 
```



这里我们会对被@RpcScan注解的class或者method做一些事情，什么事情呢？

没错，就是获取当前用户Spring的上下文，然后注入被@RpcService注解的类和我们rpc-framework-core包中或者其他包中的bean



CustomScannerRegistrar：向用户的Spring上下文中注入需要的bean



```
1. @Slf4j 

2. public class CustomScannerRegistrar implements ImportBeanDefinitionRegistrar, ResourceLoaderAware { 

3.   private static final String SPRING_BEAN_BASE_PACKAGE = "com.zhanghui.spring"; 

4.  

5.   private static final String NETTY_SERVER_PACKAGE = "com.zhanghui.remoting.transport.netty.server"; 

6.  

7.   private static final String BASE_PACKAGE_ATTRIBUTE_NAME = "basePackage"; 

8.  

9.   private ResourceLoader resourceLoader; 

10.  

11.   @Override 

12.   public void setResourceLoader(ResourceLoader resourceLoader) { 

13.     this.resourceLoader = resourceLoader; 

14.   } 

15.  

16.   @Override 

17.   public void registerBeanDefinitions(AnnotationMetadata classMetadata, BeanDefinitionRegistry registry) { 

18.  

19.     // get the attributes and values of @RpcScan annotation 

20.     AnnotationAttributes rpcScanAnnotationAttributes = AnnotationAttributes.fromMap(classMetadata.getAnnotationAttributes(RpcScan.class.getName())); 

21.  

22.     String[] rpcScanPackages = new String[0]; 

23.  

24.     if (rpcScanAnnotationAttributes != null) { 

25.       rpcScanPackages = rpcScanAnnotationAttributes.getStringArray(BASE_PACKAGE_ATTRIBUTE_NAME); 

26.     } 

27.  

28.     // default scan packages 

29.     if (rpcScanPackages.length == 0) { 

30.       rpcScanPackages = new String[]{((StandardAnnotationMetadata) classMetadata).getIntrospectedClass().getPackage().getName()}; 

31.     } 

32.  

33.     // customize scanner for scan the specified annotation 

34.     CustomScan rpcServiceScanner = new CustomScan(registry, RpcService.class); 

35.     CustomScan springBeanScanner = new CustomScan(registry, Component.class); 

36.  

37.     // scan the class which was annotated by @RpcService 

38.     int rpcServiceAnnoCount = rpcServiceScanner.scan(rpcScanPackages); 

39.     log.info("rpcServiceScanner扫描的数量 [{}]", rpcServiceAnnoCount); 

40.  

41.     // scan the SpringBeanPostProcessor to spring lifestyle 

42.     int springBeanAnnoCount = springBeanScanner.scan(SPRING_BEAN_BASE_PACKAGE,NETTY_SERVER_PACKAGE); 

43.     log.info("springBeanScanner扫描的数量 [{}]", springBeanAnnoCount); 

44.   } 

45. } 
```



实现ResourceLoaderAware接口获取当前的ResourceLoader

实现ImportBeanDefinitionRegistrar接口注册BeanDefinition



这里我们自定义CustomScan在basePackage下扫描我们指定的注解@RpcService和@Component

CustomScan：指定BeanDefinitionRegistry和Annotation在basePackage下进行扫描



```
1. public class CustomScan extends ClassPathBeanDefinitionScanner { 

2.  

3.   public CustomScan(BeanDefinitionRegistry registry, Class<? extends Annotation> annoType) { 

4.     super(registry); 

5.     super.addIncludeFilter(new AnnotationTypeFilter(annoType)); 

6.   } 

7.  

8.   @Override 

9.   public int scan(String... basePackages) { 

10.     return super.scan(basePackages); 

11.   } 

12. } 
```



需要实现ClassPathBeanDefinitionScanner接口实现scan操作



至此我们的简易版的rpc-framework已经讲解完毕

接下来是**测试环节，这里仅用于测试**



#### **3. open-api**



```
1. public interface HelloService { 

2.   String hello(Hello hello); 

3. } 
```



#### **4. example-server**



HelloServiceImpl：需要暴露的服务



```
1. @RpcService(group = "test1", version = "version1") 

2. public class HelloServiceImpl implements HelloService { 

3.  

4.   static { 

5.     System.out.println("HelloServiceImpl被创建"); 

6.   } 

7.  

8.   @Override 

9.   public String hello(Hello hello) { 

10.     log.info("HelloServiceImpl收到: {}.", hello.getMessage()); 

11.     String result = "Hello description is " + hello.getDescription(); 

12.     log.info("HelloServiceImpl返回: {}.", result); 

13.     return result; 

14.   } 

15. } 
```



Netty Server方式启动



```
1. @RpcScan(basePackage = {"com.zhanghui.service"}) 

2. public class NettyServerMain { 

3.   public static void main(String[] args) { 

4.     // Register service via annotation 

5.     AnnotationConfigApplicationContext applicationContext = new AnnotationConfigApplicationContext(NettyServerMain.class); 

6.     NettyServer nettyServer = (NettyServer) applicationContext.getBean("nettyServer"); 

7.     // Register service manually 

8.     HelloService helloService2 = new HelloServiceImpl2(); 

9.     RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

10.         .group("test2").version("version2").build(); 

11.     nettyServer.registerService(helloService2, rpcServiceProperties); 

12.     nettyServer.start(); 

13.   } 

14. } 
```



Socket Server方式启动



```
1. public class RpcFrameworkSimpleServerMain { 

2.   public static void main(String[] args) { 

3.     HelloService helloService = new HelloServiceImpl(); 

4.     SocketServer socketRpcServer = new SocketServer(); 

5.     RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

6.         .group("test2").version("version2").build(); 

7.     socketRpcServer.registerService(helloService, rpcServiceProperties); 

8.     socketRpcServer.start(); 

9.   } 

10. } 
```



#### **5. example-client**



HelloController：请求示例



```
1. @Component 

2. public class HelloController { 

3.  

4.   @RpcReference(version = "version1", group = "test1") 

5.   private HelloService helloService; 

6.  

7.   public void test() throws InterruptedException { 

8.     String hello = this.helloService.hello(new Hello("111", "222")); 

9. //    //如需使用 assert 断言，需要在 VM options 添加参数：-ea 

10. //    assert "Hello description is 222".equals(hello); 

11.     Thread.sleep(12000); 

12.     for (int i = 0; i < 10; i++) { 

13.       System.out.println(helloService.hello(new Hello("111", "222"))); 

14.     } 

15.   } 

16. } 
```



Netty Client方式启动，调用请求



```
1. @RpcScan(basePackage = {"com.zhanghui"}) 

2. public class NettyClientMain { 

3.  

4.   public static void main(String[] args) throws Exception { 

5.     AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext(NettyClientMain.class); 

6.     HelloController controller = (HelloController) context.getBean("helloController"); 

7.     controller.test(); 

8.   } 

9.  

10. } 
```



Socket Client方式启动，调用请求



```
1. public class RpcFrameworkSimpleClientMain { 

2.   public static void main(String[] args) { 

3.     ClientTransport clientTransport = new SocketClientTransport(); 

4.     RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

5.         .group("test2").version("version2").build(); 

6.     RpcClientProxy rpcClientProxy = new RpcClientProxy(clientTransport, rpcServiceProperties); 

7.     HelloService helloService = rpcClientProxy.getProxy(HelloService.class); 

8.     String hello = helloService.hello(new Hello("111", "222")); 

9.     System.out.println(hello); 

10.   } 

11. } 
```



#### **6. 总结**



对于rpc通信框架简单的原理就是两端的通信，消费端拿着方法名、类名、参数值去向服务端要结果。

重点在于设计这其中的细节部分



比如说



1）**缓存**，在rpc-framework大量使用缓存结果，保证系统的高可用。

比如向消费端zk端查找服务地址，消费端向指定channel发送请求等。



2）**长连接**，对于服务端和消费端为了避免建立连接的开销，可以通过心跳机制保持必要的长连接。



3）**通信协议**的编写，通信通信，这最基本的报文格式编码和解码该怎么设计。



4）如何让消费端像调用本地方法一样调用远程方法，这就涉及到**远程代理**了。



5）结合到**Spring**的生命周期我们可以做出更多的设计，比如BeanPostProcessor。



6）CompletableFuture在异步多线程环境下的使用。



7）**线程池**的合理使用，对于Netty使用EventLoopGroup天然使用线程池，而Socket场景则需要我们创建线程池去处理请求。



最后是该项目目前并不完善，比如基本的monitor组件并没有创建，后期根据情况会对项目进行更近一步的优化