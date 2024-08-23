手写rpc通信框架之基于xml配置
2024-08-22
记录一次手写Rpc通信框架的拓展部分
06.jpg
造轮子系列
huizhang43

这一章主要实现自定义rpc框架基于xml配置的方式实现服务的注册和消费

顺便更改测试项目到SpringBoot环境下，由SpringBoot管理Spring



#### **1. 自定义xml格式**



首先我们需要申明xml的格式，可以自定义标签名和校验规则，核心是编写rpc.xsd文件

这里简单介绍下让我们编写的rpc.xsd生效和自动解析xml



##### **1）编写rpc.xsd**



如



```
1. <?xml version="1.0" encoding="UTF-8" ?> 

2. <schema xmlns="http://www.w3.org/2001/XMLSchema" 

3.   targetNamespace="http://www.zhangh.com/schema/rpc" 

4.     elementFormDefault="qualified"> 

5.  

6.   <element name="user"> 

7.     <complexType> 

8.       <attribute name="id" type="string" /> 

9.       <attribute name="name" type="string" /> 

10.       <attribute name="email" type="string" /> 

11.     </complexType> 

12.   </element> 

13. </schema> 
```



##### **2）注册rpc.xsd**



配置rpc.xsd的命名空间和让它解析生效，在文件META-INF/Spring.schemas中加入



```
1. http://www.zhangh.com/schema/rpc.xsd=com.zhangh.xsd/schema/rpc.xsd 
```



##### **3）编写解析类（直接映射成Bean）**



实现BeanDefinitionParser接口，定义解析规则



```
1. public class RpcBeanDefinitionParser extends AbstractSingleBeanDefinitionParser { 

2.  

3.   protected Class getBeanClass(Element element){ 

4.     return User.class; 

5.   } 

6.   protected void doParse(Element element, BeanDefinitionBuilder bean) { 

7.     String userName = element.getAttribute("name"); 

8.     String email = element.getAttribute("email"); 

9.  

10.     if(StringUtils.hasText(userName)) { 

11.       bean.addPropertyValue("name", userName); 

12.     } 

13.  

14.     if (StringUtils.hasText(email)) { 

15.       bean.addPropertyValue("email", email); 

16.     } 

17.   } 

18. } 
```



扩展NamespaceHandlerSupport类：注册解析类



```
1. public class MyNamespaceHandler extends NamespaceHandlerSupport { 

2.   public void init() { 

3.     registerBeanDefinitionParser("rpc",new RpcBeanDefinitionParser());

4.   } 

5. } 
```



##### **4）注册解析器**



在META-INF/Spring.handlers文件中加入：



```
1. http://www.zhangh.com/schema/rpc=com.zhangh.xsd.paser.MyNamespaceHandler 
```



当引用http://www.zhangh.com/schema/rpc 时会使用MyNamespaceHandler解析引用对象

这里我偷个懒没有自定义xml格式，直接用的dubbo的，而且我们需要解析的过程也不是简单将xml里面的内容封装成Bean并注册到Spring中，所以上面的内容仅供学习。



#### **2. 解析xml文件**



这里我本来想学Spring来个XmlBeanDefinitionReader的，后来优化掉了，因为一直考虑这个xml文件路径怎么传进来



最后发现**Spring有个@ImportResource注解**里面可以定义解析器，所以最后实现起来是这样的



```
1. @Slf4j 

2. public class RpcBeanDefinitionReader extends AbstractBeanDefinitionReader { 

3.  

4.   private final RpcParserResult rpcParserResult = new RpcParserResult(); 

5.  

6.   private final ServiceProvider serviceProvider; 

7.  

8.   private final ClientTransport clientTransport; 

9.  

10.   private final BeanDefinitionRegistry registry; 

11.  

12.   public static final String DUBBO_NAMESPACE_URI = "http://code.alibabatech.com/schema/dubbo"; 

13.  

14.   public static final String SERVICE_ELEMENT = "service"; 

15.  

16.   public static final String CONSUMER_ELEMENT = "reference"; 

17.  

18.   public static final String ID_ATTRIBUTE = "id"; 

19.  

20.   public static final String GROUP_ATTRIBUTE = "group"; 

21.  

22.   public static final String VERSION_ATTRIBUTE = "version"; 

23.  

24.   public static final String REF_ATTRIBUTE = "ref"; 

25.  

26.   public static final String INTERFACE_ATTRIBUTE = "interface"; 

27.  

28.   public RpcBeanDefinitionReader(BeanDefinitionRegistry registry){ 

29.     super(registry); 

30.     this.registry = registry; 

31.     this.serviceProvider = SingletonFactory.getInstance(ServiceProviderImpl.class); 

32.     this.clientTransport = ExtensionLoader.getExtensionLoader(ClientTransport.class).getExtension("nettyClientTransport"); 

33.   } 

34.  

35.   @Override 

36.   public int loadBeanDefinitions(Resource resource) throws BeanDefinitionStoreException { 

37.  

38.     int beanCount = registry.getBeanDefinitionCount(); 

39.  

40.     if (resource == null || !resource.exists()) { 

41.       throw new RpcException(RpcErrorMessageEnum.INIT_RESOURCE_NOT_NULL); 

42.     } 

43.  

44.     try (InputStream is = resource.getInputStream()) { 

45.  

46.       SAXReader reader = new SAXReader(); 

47.       Document document = reader.read(is); 

48.       Element root = document.getRootElement(); 

49.  

50.       Iterator<Element> iterator = root.elements().iterator(); 

51.       while (iterator.hasNext()) { 

52.         Element element = iterator.next(); 

53.         String namespaceUri = element.getNamespaceURI(); 

54.         if (isDubboNamespace(namespaceUri)) { 

55.           parseDubboElement(element); 

56.         } 

57.       } 

58.     } catch (IOException | DocumentException ex) { 

59.       log.error("occur exception when parse the resource [{}]", resource.getDescription()); 

60.     } 

61.  

62.     this.doRegisterServce(); 

63.     this.doCreateProxy(); 

64.  

65.     log.info("has registred beanDefinition nums [{}])", registry.getBeanDefinitionCount() - beanCount); 

66.     return registry.getBeanDefinitionCount() - beanCount; 

67.   } 

68.  

69.   private void parseDubboElement(Element ele) { 

70.     if (SERVICE_ELEMENT.equals(ele.getName())) { 

71.       String interfaceName = ele.attributeValue(INTERFACE_ATTRIBUTE); 

72.       try { 

73.         if(Class.forName(interfaceName) == null){ 

74.           throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NOT_FOUND,interfaceName); 

75.         } 

76.       } catch (ClassNotFoundException e) { 

77.         throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NOT_FOUND,interfaceName); 

78.       } 

79.  

80.       String ref = ele.attributeValue(REF_ATTRIBUTE); 

81.       String group = ele.attributeValue(GROUP_ATTRIBUTE); 

82.       String version = ele.attributeValue(VERSION_ATTRIBUTE); 

83.  

84.       RpcProvider rpcProvider = RpcProvider.builder() 

85.           .interfaceName(interfaceName) 

86.           .group(group) 

87.           .version(version) 

88.           .ref(ref).build(); 

89.  

90.       this.rpcParserResult.addRpcService(rpcProvider); 

91.     } else if (CONSUMER_ELEMENT.equals(ele.getName())) { 

92.       String interfaceName = ele.attributeValue(INTERFACE_ATTRIBUTE); 

93.  

94.       try { 

95.         if(Class.forName(interfaceName) == null){ 

96.           throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NOT_FOUND,interfaceName); 

97.         } 

98.       } catch (ClassNotFoundException e) { 

99.         throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NOT_FOUND,interfaceName); 

100.       } 

101.  

102.       String id = ele.attributeValue(ID_ATTRIBUTE); 

103.       String group = ele.attributeValue(GROUP_ATTRIBUTE); 

104.       String version = ele.attributeValue(VERSION_ATTRIBUTE); 

105.  

106.       RpcConsumer rpcConsumer = RpcConsumer.builder() 

107.           .interfaceName(interfaceName) 

108.           .group(group) 

109.           .version(version) 

110.           .id(id).build(); 

111. 

112.       this.rpcParserResult.addRpcConsumer(rpcConsumer); 

113.     } 

114.   } 

115.  

116.   /** 

117.   * 判断命名方式是不是dubbo 

118.   */ 

119.   private boolean isDubboNamespace(String namespaceUri) { 

120.     return (!StringUtils.hasLength(namespaceUri) || DUBBO_NAMESPACE_URI.equals(namespaceUri)); 

121.   } 

122.  

123.   public void doRegisterServce() { 

124.     Iterator<RpcProvider> iterator = this.rpcParserResult.listRpcServices(); 

125.  

126.     while (iterator.hasNext()) { 

127.       RpcProvider rpcProvider = iterator.next(); 

128.       this.registerServie(rpcProvider); 

129.     } 

130.   } 

131.  

132.   /** 

133.   * 生成代理对象 

134.   */ 

135.   public void doCreateProxy() { 

136.     Iterator<RpcConsumer> iterator = this.rpcParserResult.listRpcConsumers(); 

137.  

138.     while (iterator.hasNext()) { 

139.       RpcConsumer rpcConsumer = iterator.next(); 

140.       RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

141.           .version(rpcConsumer.getVersion()).group(rpcConsumer.getGroup()).build(); 

142.       RpcClientProxy clientProxy = new RpcClientProxy(clientTransport, rpcServiceProperties); 

143.  

144.       try { 

145.         Class targetClass = Class.forName(rpcConsumer.getInterfaceName()); 

146.        Object proxyBean = clientProxy.getProxy(targetClass); 

147.         ((DefaultListableBeanFactory)registry).registerSingleton(rpcConsumer.getId(),proxyBean); 

148.       } catch (ClassNotFoundException e) { 

149.         throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NOT_FOUND, rpcConsumer.getInterfaceName()); 

150.       } 

151.     } 

152.   } 

153.  

154.   /** 

155.   * 向zk注册服务 

156.   */ 

157.   private void registerServie(RpcProvider rpcProvider) { 

158.  

159.     RpcServiceProperties rpcServiceProperties = RpcServiceProperties.builder() 

160.         .version(rpcProvider.getVersion()).group(rpcProvider.getGroup()) 

161.         .serviceName(rpcProvider.getInterfaceName()).build(); 

162.  

163.     String refBeanName = rpcProvider.getRef(); 

164.  

165.     Object refBean = ((DefaultListableBeanFactory)registry).getBean(refBeanName); 

166.  

167.     if (refBean == null) { 

168.       log.error("can`t find bean with beanName [{}]", refBeanName); 

169.       throw new ResourceParserException(ParserErrorMessageEnum.SERVICE_NO_REALIZE, refBeanName); 

170.     } 

171.     serviceProvider.publishService(refBean, rpcServiceProperties); 

172.   } 

173. } 
```



实现起来基本的思路就是：



1）将xml文件中的<dubbo:service>标签解析成RpcProvider并通过ServiceProvider给它publish出去。



2）将xml文件中的<dubbo:reference>标签解析成RpcConsumer并通过RpcClientProxy给它创建代理对象并放到Spring容器中去



注意这个时候我们使用消费服务的时候**只能通过@Resource**方法获取，因为我们放进Spring的是代理类



```
1. Class targetClass = Class.forName(rpcConsumer.getInterfaceName()); 

2.  

3. Object proxyBean = clientProxy.getProxy(targetClass); 

4.  

5. ((DefaultListableBeanFactory)registry).registerSingleton(rpcConsumer.getId(),proxyBean); 
```



这样之后我们通过在SpringBoot的启动类加上@ImportResource注解即可完成自动解析



```
1. @ImportResource(locations ="classpath:dubbo-consumer.xml", reader = RpcBeanDefinitionReader.class) 

2. public class HelloClientApplication { 

3.  

4.   public static void main(String[] args) { 

5.  

6.     SpringApplication.run(HelloClientApplication.class, args); 

7.   } 

8.  

9.  

10. } 
```



#### **3. 配置服务端**



服务端和消费端的区别在于服务端会启动一个netty或者socket一直去监听端口，所以需要加以区分

这里我的处理方式就是通过@EnableRpcServer注解去实现



@EnableRpcServer：是否开启服务端



```
1. @Target(ElementType.TYPE) 

2. @Retention(RetentionPolicy.RUNTIME) 

3. @Documented 

4. @Import(CustomStarterRegistrar.class) 

5. public @interface EnableRpcServer { 

6.  

7.   boolean isServer() default false; 

8.  

9.   ServiceProviderEnum providerType() default ServiceProviderEnum.NETTY_SERVER; 

10.  

11. } 
```



这里我们希望实现注解的自动解析和相关操作，引入一个ImportBeanDefinitionRegistrar的扩展类，这个类本意是希望引入我们自己的Bean到Spring中，可以通过扫描或者手动添加的方式，因为我们可以拿到一个BeanDefinitionRegistry。



在@RpcScan注解中我们就是通过扩展ImportBeanDefinitionRegistrar类，用扫描方式将我们核心里spring注解修饰的类和自定义注解类修改的类注入到当前Spring上下文中



```
1. CustomScan rpcServiceScanner = new CustomScan(registry, RpcService.class); 

2. CustomScan springBeanScanner = new CustomScan(registry, Component.class); 

3.  

4. // scan the class which was annotated by @RpcService 

5. int rpcServiceAnnoCount = rpcServiceScanner.scan(rpcScanPackages); 

6. log.info("rpcServiceScanner扫描的数量 [{}]", rpcServiceAnnoCount); 

7.  

8. // scan the SpringBeanPostProcessor to spring lifestyle 

9. int springBeanAnnoCount = springBeanScanner.scan(SPRING_BEAN_BASE_PACKAGE); 

10. log.info("springBeanScanner扫描的数量 [{}]", springBeanAnnoCount); 
```



除了ImportBeanDefinitionRegistrar接口还有一个ImportSelector接口，这个类的意思就是可以通过注解里面的内容，一般有条件或者默认值，有选择的向Spring上下文注入Configuration类，实质也是Bean



比如@EnableCaching中



```
1. @Target(ElementType.TYPE) 

2. @Retention(RetentionPolicy.RUNTIME) 

3. @Documented 

4. @Import(CachingConfigurationSelector.class) 

5. public @interface EnableCaching { 

6.   //... 

7.  

8.   AdviceMode mode() default AdviceMode.PROXY; 

9.  

10.   //... 

11. } 

12.  

13. //AdviceModeImportSelector是ImportSelector的扩展类 

14. public class CachingConfigurationSelector extends AdviceModeImportSelector<EnableCaching> { 

15.      

16.   //... 

17.      

18.   // 这里返回结果是需要注入Spring的类名集合 

19.   @Override 

20.   public String[] selectImports(AdviceMode adviceMode) { 

21.     switch (adviceMode) { 

22.       case PROXY: 

23.         return getProxyImports(); 

24.       case ASPECTJ: 

25.         return getAspectJImports(); 

26.       default: 

27.         return null; 

28.     } 

29.   } 

30.      

31.   //... 

32.  

33. } 
```



好了，言归正传，看一下我们的ImportBeanDefinitionRegistrar 扩展类实现了什么内容



其实很简单，就是**启动Server**



```
1. @Slf4j 

2. public class CustomStarterRegistrar implements ImportBeanDefinitionRegistrar { 

3.  

4.   private static final String PROVIDER_TYPE = "providerType"; 

5.  

6.   private static final String IS_SERVER = "isServer"; 

7.  

8.  

9.   @Override 

10.   public void registerBeanDefinitions(AnnotationMetadata classMetadata, BeanDefinitionRegistry registry) { 

11.  

12.     // get the attributes and values of @RpcScan annotation 

13.     AnnotationAttributes annotationAttributes = AnnotationAttributes.fromMap(classMetadata.getAnnotationAttributes(EnableRpcServer.class.getName())); 

14.  

15.     boolean isServer = annotationAttributes.getBoolean(IS_SERVER); 

16.  

17.     ServiceProviderEnum providerEnum = annotationAttributes.getEnum(PROVIDER_TYPE); 

18.  

19.     if(isServer){ 

20.       if(providerEnum == ServiceProviderEnum.NETTY_SERVER){ 

21.         new NettyServer().start(); 

22.       }else if(providerEnum == ServiceProviderEnum.SOCKET_SERVER){ 

23.         new SocketServer().start(); 

24.       } 

25.     } 

26.   } 

27. } 
```



到此，我们就完成了这次优化的内容



#### **4. 总结**



1）第一个就是我们想自定义xml文件的时候怎么做，xsd标签怎么让它生效，自动化解析的过程



2）借助@ImportSource可以自定义解析过程，在解析过程中可以拿到BeanDefinitionRegistry完成对Spring上下文的操作。



3）使用@Import可以引入ImportBeanDefinitionRegistrar和ImportSelector的扩展类来实现对Spring上下文的操作，在这个过程中也可以拿到BeanDefinitionRegistry



4）在设计过程中考虑到了一些设计问题，比如抽象、解耦合，解决问题的思路从根源出发，下次尝试下使用TDD开发模式。



期待下一次的优化！