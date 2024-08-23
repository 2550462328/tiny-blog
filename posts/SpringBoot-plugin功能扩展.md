SpringBoot-plugin功能扩展
2024-08-22
基于SpringBoot-plugin项目的功能扩展。
03.jpg
实践原理
huizhang43

#### **1、WebMvc的扩展**



关键字：**WebMvcConfigurer、ResourceResolver、Resource、DelegatingWebMvcConfiguration**

工具类：Files



在springboot-plugin中有个静态资源扩展的需求：怎么访问到插件中的静态资源？

具体思路就是先配置插件访问路径拦截规则，也就是声明什么样的请求可以视为对插件静态资源的访问。



这里我们要实现**WebMvcConfigurer**，定义资源处理规则



```
1. public class ResourceWebMvcConfigurer implements WebMvcConfigurer { 

2.  

3.   @Override

4.   public void addResourceHandlers(ResourceHandlerRegistry registry) {

5.     String pathPattern = "/" + SpringBootStaticResourceExtension.getPluginResourcePrefix() + "/**";

6.     // 设置资源请求拦截路径的前缀

7.     ResourceHandlerRegistration resourceHandlerRegistration = registry.addResourceHandler(pathPattern);

8. 

9.     // 设置对资源的缓存

10.     CacheControl cacheControl = SpringBootStaticResourceExtension.getCacheControl();

11.     if(cacheControl != null){

12.       resourceHandlerRegistration.setCacheControl(cacheControl);

13.     }else{

14.       resourceHandlerRegistration.setCacheControl(CacheControl.noStore());

15.     }

16.     resourceHandlerRegistration.resourceChain(false).addResolver(new PluginResourceResolver());

17.   }  

18. } 
```



其次就是在拦截到对应请求后，怎么根据请求路径查找到它对应的资源呢？



这里我们要实现**ResourceResolver**，定义资源解析规则



```
1. public class PluginResourceResolver implements ResourceResolver { 

2.  

3.   @Override 

4.   public Resource resolveResource(HttpServletRequest request, String requestPath, List<? extends Resource> locations, ResourceResolverChain chain) { 

5.     int startIndex = requestPath.startsWith("/") ? 1 : 0;

6.     int endIndex = requestPath.indexOf("/", 1);

7. 

8.     if (endIndex != -1) {

9.       String pluginId = requestPath.substring(startIndex, endIndex);

10.       String partialPath = requestPath.substring(endIndex + 1);

11. 

12.       PluginStaticResource pluginStaticResource = PLUGIN_STATIC_RESOURCE_MAP.get(pluginId);

13.       if (pluginStaticResource == null) {

14.         return null;

15.       }

16. 

17.       // 跟据pluginId计算缓存key

18.       String cacheKey = computeKey(pluginId);

19.       // 有缓存直接取缓存

20.       if (pluginStaticResource.hasCacheResource(pluginId)) {

21.         return pluginStaticResource.getCacheResource(pluginId);

22.       }

23. 

24.       Resource resource;

25. 

26.       // 基于classpath路径解析出插件Resource

27.       resource = resolveResourceFromClassPath(pluginStaticResource,partialPath);

28.       if(resource != null){

29.         pluginStaticResource.addCacheResourceIfAbsent(cacheKey,resource);

30.         return resource;

31.       }

32. 

33.       // 基于File文件路径加载插件Resource

34.       resource = resolveResourceFromFilePath(pluginStaticResource,partialPath);

35.       if(resource != null){

36.         pluginStaticResource.addCacheResourceIfAbsent(cacheKey,resource);

37.         return resource;

38.       }

39. 

40.       return null;

41.     }

42.     // 责任链模式

43.     return chain.resolveResource(request, requestPath, locations);

44.   } 

45. } 
```



这里会根据插件中对静态资源的配置（保存路径）PluginStaticResource，从File路径和ClassPath路径两个维度去查找用户需要访问的静态资源Resource。

这里有一点需要说明的是，在MVC和Servlet中用的比较多的一种设计模式是责任链模式，比如说这里的



```
return chain.resolveResource(request, requestPath, locations);
```



也就是当前资源或者路径我加载不了或者匹配不上，可以交由下游去继续执行。



最后也是最重要的一步就是将我们自定义的WebMvcConfigurer加入到主版本的MVC环境中，这里是**DelegatingWebMvcConfiguration**



```
1. @Override 

2. public void initialize(ApplicationContext mainApplicationContext) throws Exception { 

3.   List<WebMvcConfigurer> webMvcConfigurers = Lists.newArrayList(new ResourceWebMvcConfigurer()); 

4.   // webMvc的处理委托类 

5.   DelegatingWebMvcConfiguration delegatingWebMvcConfiguration = mainApplicationContext.getBean(DelegatingWebMvcConfiguration.class); 

6.   delegatingWebMvcConfiguration.setConfigurers(webMvcConfigurers); 

7. } 
```



到此WebMvc扩展结束



#### **2、Mybatis的扩展**



关键字：**SqlSessionFactoryBean**、**SqlSessionFactory**、**Configuration**、**SqSessionTemplate**、**SqlSession**、**MybatisFactoryBean**

工具类：AnnotationConfigUtils、BeanDefinitionReaderUtils、ScopeMetadataResolver、ResourcePatternResolver、MetadataReaderFactory



在springboot-plugin有个需求：需要让插件支持Mybatis对数据库操作

前面springboot-plugin原理一节中我们了解到，pluginApplicationContext是个“空房子”，如果要让它支持Mybatis，首先我们需要知道Mybatis的原理是什么？



正常我们在使用Mybatis的时候，有一个*Mapper.class刚好一个*Mapper.xml文件，然后在*Mapper.xml中写sql执行语句，最后将*Mapper.class类注入到我们待使用的类中。



那背后的原理是什么呢？



*Mapper.xml文件会被解析到一个重量级的类Configuration中，其中：

 <parameterMap>标签会被解析为 ParameterMap 对象，其中每个子元素会被解析成ParameterMapping对象。

 <resultMap>标签会被解析成ResultMap对象，其中每个子元素会被解析成ResultMapping对象。

 <select>、<insert>、<update>、<delete>标签都会被解析成MappedStatement对象，标签内的sql会被解析成BoundSql对象。



*Mapper.class里面的select、insert、delete、update方法会通过*Mapper.xml的namespace标签值 + 方法名进行关联。



*Mapper.class 真正注入到Spring中是一个MapperFactoryBean，通过getObject返回一个MapperProxy对象，在真正执行的时候，会通过MapperFactoryBean里的SqlSessionFactroy生成SqlSession对象，由SqlSession真正去执行MappedStatement里的SqlSource。



综上所述，我们实现在插件中支持Mybatis的本质是将插件中的*Mapper.class以MapperFactoryBean的方式装配到pluginApplicationContext中



首先我们需要SqlSessionFactoryBean去生成SqlSessionFactrory



```
1. @Override 

2. public void registry(PluginRegistryInfo pluginRegistryInfo) throws Exception { 

3.   List<Object> configFileObjects = pluginRegistryInfo.getConfigFileObjects(); 

4.   SpringBootMybatisConfig springBootMybatisConfig = getMybatisConfig(configFileObjects); 

5.   if (springBootMybatisConfig == null) { 

6.     return; 

7.   } 

8.  

9.   SqlSessionFactoryBean sqlSessionFactoryBean =newSqlSessionFactoryBean(); 

10.  

11.   if (springBootMybatisConfig.enableOneselfConfig()) { 

12.     // 自己配置SqlSessionFactoryBean 

13.     springBootMybatisConfig.oneselfConfig(sqlSessionFactoryBean); 

14.   }  else {

15.       // 使用主版本里的SqlSession

16.       ApplicationContext mainApplicationContext = pluginRegistryInfo.getMainApplicationContext();

17.       PluginMybatisCoreConfig pluginMybatisCoreConfig = new PluginMybatisCoreConfig(mainApplicationContext);

18. 

19.       DataSource dataSource = pluginMybatisCoreConfig.getDataSource();

20.       if (dataSource != null) {

21.         // 设置数据库连接池     sqlSessionFactoryBean.setDataSource(pluginMybatisCoreConfig.getDataSource());

22.       }

23. 

24.       Configuration configuration = pluginMybatisCoreConfig.getMybatisConfiguration();

25.       // 设置Mybatis配置信息

26.       sqlSessionFactoryBean.setConfiguration(configuration);

27. 

28.       Interceptor[] interceptors = pluginMybatisCoreConfig.getInterceptors();

29.       if (interceptors != null && interceptors.length > 0) {

30.         // 设置Mybatis自定义插件拦截器信息

31.         sqlSessionFactoryBean.setPlugins(interceptors);

32.       }

33. 

34.       DatabaseIdProvider databaseIdProvider = pluginMybatisCoreConfig.getDatabaseIdProvider();

35.       if (databaseIdProvider != null) {

36.         // 设置数据库唯一标识生成器信息

37.     sqlSessionFactoryBean.setDatabaseIdProvider(databaseIdProvider);

38.       }

39. 

40.       LanguageDriver[] languageDrivers = pluginMybatisCoreConfig.getLanguageDrivers();

41.       if (languageDrivers != null && languageDrivers.length > 0) {

42.         for (LanguageDriver languageDriver : languageDrivers) {

43.           // 注册Mybatis的自定义sql解析

44.     configuration.getLanguageRegistry().register(languageDriver);

45.         }

46.       }

47.     }

48. 

49.     PluginResourceFinder pluginResourceFinder = new PluginResourceFinder(pluginRegistryInfo);

50.     Class<?>[] aliasesClasses = pluginResourceFinder.getAliasesClasses(springBootMybatisConfig.entityPackages());

51.     // 设置数据库实体和别名

52.     sqlSessionFactoryBean.setTypeAliases(aliasesClasses);

53. 

54.     Resource[] xmlResources = pluginResourceFinder.getXmlResources(springBootMybatisConfig.xmlLocationsMatch());

55.     // 设置数据库访问xml资源

56.     sqlSessionFactoryBean.setMapperLocations(xmlResources);

57. 

58.     // 保存原有的ClassLoader用于后期还原

59.     ClassLoader defaultClassLoader = Resources.getDefaultClassLoader();

60. 

61.     try {

  Resources.setDefaultClassLoader(pluginRegistryInfo.getDefaultPluginClassLoader());

62. 

63.       SqlSessionFactory sqlSessionFactory = sqlSessionFactoryBean.getObject();

64.       Objects.requireNonNull(sqlSessionFactory);

65. 

66.       SqlSessionTemplate sqlSessionTemplate = new SqlSessionTemplate(sqlSessionFactory);

67.       MapperHandler mapperHandler = new MapperHandler();

68.       // 对单个Mapper操作

69.       mapperHandler.processMapper(pluginRegistryInfo, sqlSessionFactory, sqlSessionTemplate);

70. 

71.     } finally {

72.       Resources.setDefaultClassLoader(defaultClassLoader);

73.     }
```



这里配置SqlSessionFactoryBean一部分是从主版本里Mybatis下的Configuration中取配值信息，比如Mybatis插件、数据源、sql解析器等，另一部分是从插件版本的配置中去取，比如数据库实体类和别名、\mapper.xml资源。



取*mapper.xml资源



```
1. /** 

2. * xmlLocationPath ： 插件配置*Mapper.xml路径 

3. * resourcePatternResolver：PathMatchingResourcePatternResolver Spring的根据路径查找Resource的工具 

4. */ 

5.Resource[] loadResources = resourcePatternResolver.getResources(xmlLocationPath); 
```



取数据库实体类和别名



```
1. String resourcePath = ResourcePatternResolver.CLASSPATH_ALL_URL_PREFIX + ClassUtils.convertClassNameToResourcePath(packagePattern) + "/**/*.class"; 

2.  

3.Resource[] packageLoadResources = resourcePatternResolver.getResources(resourcePath); 

4. for(Resource resource : packageLoadResources){ 

5.   try { 

6.     // 读取Resource信息 

7.     ClassMetadata classMetadata = metadataReaderFactory.getMetadataReader(resource).getClassMetadata(); 

8.     Class<?> clazz = classLoader.loadClass(classMetadata.getClassName()); 

9.     packageEntities.add(clazz); 

10.   } catch (ClassNotFoundException e) { 

11.     e.printStackTrace(); 

12.   } 

13. } 
```



在配置好SqlSessionFactoryBean后，需要将我们的*Maper.class装配到pluginApplicationContext中



```
1. for (Class mapperClass : mapperGroupClasses) { 

2.   AnnotatedGenericBeanDefinition annotatedGenericBeanDefinition = new AnnotatedGenericBeanDefinition(mapperClass); 

3.   // 获取mapperClass中Bean的Scope 

4.   ScopeMetadata scopeMetadata = scopeMetadataResolver.resolveScopeMetadata(annotatedGenericBeanDefinition); 

5.   annotatedGenericBeanDefinition.setScope(scopeMetadata.getScopeName()); 

6.   // 生成BeanName 

7.   String mapperBeanName = beanNameGenerator.generateBeanName(annotatedGenericBeanDefinition, pluginApplicationContext); 

8.   BeanDefinitionHolder beanDefinitionHolder = new BeanDefinitionHolder(annotatedGenericBeanDefinition, mapperBeanName); 

9.  

10.   AnnotationConfigUtils.processCommonDefinitionAnnotations(annotatedGenericBeanDefinition); 

11.   // 注册Mapper的BeanDefinition 

12.   BeanDefinitionReaderUtils.registerBeanDefinition(beanDefinitionHolder, pluginApplicationContext); 

13.  

14.   // 修改BeanDefinition中的MapperClass 到 MapperFactoryBean 

15.   doInjectProperties(beanDefinitionHolder, mapperClass, sqlSessionFactory, sqlSessionTemplate); 

16.   mapperBeanNames.add(mapperBeanName); 

17. } 
```



其中修改MapperBean的BeanDefinition从MapperClass到MapperFactoryBean



```
1. GenericBeanDefinition beanDefinition = (GenericBeanDefinition) holder.getBeanDefinition(); 

2. beanDefinition.getConstructorArgumentValues().addGenericArgumentValue(mapperClass); 

3.beanDefinition.setBeanClass(org.mybatis.spring.mapper.MapperFactoryBean.class); 

4. beanDefinition.getPropertyValues().add("addToConfig", true); 

5.beanDefinition.getPropertyValues().add("sqlSessionFactory", sqlSessionFactory); 

6. beanDefinition.getPropertyValues().add("sqlSessionTemplate", sqlSessionTemplate); 

7. beanDefinition.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_BY_TYPE); 
```



到此Mybatis的扩展结束。



#### **3、SpringMVC扩展**



**关键字：RequestMappingHandlerMapping、RequestMappingInfo**

工具类：ReflectionUtils



在springboor-plugin有个需求：怎么让插件的Controller可以被外界访问到？



首先还是说明一下，pluginApplicationContext是一个“空房子”，如果你不对Controller类做特别的处理，它只能作为一个bean躺在pluginApplicationContext里。

而在说明需要做什么处理之前，我们先简单了解一下springMvc的原理，我们的controller是怎么被外界访问到的？



springMVC原理图如下：



![img](http://pcc.huitogo.club/c944ccd15bc83b6703f66904326515d5)



其中各个流程：



1）客户端（浏览器）发送请求，直接请求到 DispatcherServlet。

2）DispatcherServlet 根据请求信息调用 HandlerMapping，解析请求对应的 Handler。

3）解析到对应的 Handler（也就是我们平常说的 Controller 控制器）后，开始由 HandlerAdapter 适配器处理。

4）HandlerAdapter 会根据 Handler 来调用真正的处理器来处理请求，并处理相应的业务逻辑。

5）处理器处理完业务后，会返回一个 ModelAndView 对象，Model 是返回的数据对象，View 是个逻辑上的 View。

6）ViewResolver 会根据逻辑 View 查找实际的 View。

7）DispaterServlet 把返回的 Model 传给 View（视图渲染）。

8）把View返回给请求者。



在了解完springMVC的原理后，接下来我们需要做的事情就很简单了，只要把插件版本Controller里的RequestMappingInfo（被@RequestMapping注解的）装配到主版本的HandlerMapping中，这样在外界访问的时候就可以根据HandlerMapping找到插件里的Handler，最后由HandlerAdapter调用插件Handler里的业务逻辑。



这一部分的代码如下：



```
1. /** 

2. * 注册当前Controller类到主版本的mvc环境中 

3. * 

4. * @param pluginRegistryInfo 

5. * @param controllerClass 

6. * @return 

7. */ 

8. private ControllerWrapper doRegistry(PluginRegistryInfo pluginRegistryInfo, Class<?> controllerClass) { 

9.   String pluginId = pluginRegistryInfo.getPluginWrapper().getPluginId(); 

10.   GenericApplicationContext pluginApplicationContext = pluginRegistryInfo.getPluginApplicationContext(); 

11.  

12.   Object controllerBean = pluginApplicationContext.getBean(controllerClass); 

13.   ControllerWrapper controllerWrapper = new ControllerWrapper(); 

14.   controllerWrapper.setBeanClass(controllerClass); 

15.   Set<RequestMappingInfo> requestMappingInfos = Sets.newHashSet(); 

16.  

17.   try { 

18.     //修改controllerClass中RequestMapping映射路径 

19.     setPathPrefix(pluginId, controllerClass); 

20.   // 通过反射获取RequestMappingHandlerMapping的getMappingForMethod字段

21.     Method getMappingForMethod = ReflectionUtils.findMethod(RequestMappingHandlerMapping.class, "getMappingForMethod",Method.class,Class.class); 

22.     getMappingForMethod.setAccessible(true); 

23.  

24.     // 遍历controllerClass所有Method 过滤出被RequestMapping注释的方法 然后注册到主版本的RequestMapping上下文中去 

25.     Method[] targetMethods = controllerClass.getMethods(); 

26.     for (Method targetMethod : targetMethods) { 

27.       if (isHaveRequestMapping(targetMethod)) { 

28.         RequestMappingInfo requestMappingInfo = (RequestMappingInfo) getMappingForMethod.invoke(requestMappingHandlerMapping, targetMethod, controllerClass);   

29.         requestMappingHandlerMapping.registerMapping(requestMappingInfo, controllerBean, targetMethod); 

30.         requestMappingInfos.add(requestMappingInfo); 

31.       } 

32.     } 

33.   } catch (Exception e) { 

34.     e.printStackTrace(); 

35.   } 

36.   controllerWrapper.setRequestMappingInfos(requestMappingInfos); 

37.   return controllerWrapper; 

38. } 
```



当指定插件被停用的时候，我们还要从版本中移除被停用插件中的RequestMappingInfo



```
1. /** 

2. * 从主版本的mvc环境中去除Controller 

3. */ 

4. private void doUnRegistry(ControllerWrapper controllerWrapper){ 

5.      Set<RequestMappingInfo> requestMappingInfos = controllerWrapper.getRequestMappingInfos();

6.     if(requestMappingInfos != null && requestMappingInfos.size() > 0) {

7.       requestMappingInfos.forEach(requestMappingHandlerMapping::unregisterMapping);

8.     }

9. } 
```



到此SpringMVC扩展结束。



#### **4、yml读取成对象**



**关键字：YAMLParser、TreeTraversingParser、YAMLFactory**

工具类：ObjectMapper



在springboot-plugin中有个需求：解析被@ConfigDefinition注解的对象，将ConfigDefinition里value的配置文件的值赋给被@ConfigDefinition注解的对象。



如下方：



1. @ConfigDefinition("plugin1.yml")
2. public class Plugin1Config {
3. 
4. private String name;
5. }



这个类似于这样：



```
1. @Configuration 

2. public class Plugin1Config { 

3.  

4.   @Value("name") 

5.   private String name; 

6. } 
```



实现思路就是读取plugin1.yml文件的key-value成一个对象注入到pluginApplicationContext中。

解析plugin.yml文件到对象的代码如下：



```
1. /** 

2. * 从resource中解析出configDefinitionClass的实体类 

3. * 

4. * @param resource plugin.yml文件 

5. * @param configDefinitionClass 被@ConfigDefinition注解的类 

6. * @return 

7. * @throws Exception 

8. */ 

9. @Override 

10. protected Object parse(Resource resource, Class configDefinitionClass) throws Exception { 

11.   InputStream inputStream = null; 

12.   YAMLParser yamlParser = null; 

13.   TreeTraversingParser treeTraversingParser = null; 

14.  

15.   try { 

16.     inputStream = resource.getInputStream(); 

17.     yamlParser = yamlFactory.createParser(inputStream); 

18.     final JsonNode root = objectMapper.readTree(yamlParser); 

19.     if(root == null){ 

20.       return configDefinitionClass.newInstance(); 

21.     } 

22.     treeTraversingParser = new TreeTraversingParser(root); 

23.     returnobjectMapper.readValue(treeTraversingParser,configDefinitionClass); 

24.   }finally { 

25.     if(treeTraversingParser != null){ 

26.       treeTraversingParser.close(); 

27.     } 

28.     if(yamlParser != null){ 

29.       yamlParser.close(); 

30.     } 

31.     if(inputStream != null){ 

32.       inputStream.close(); 

33.     } 

34.   } 

35.  

36. } 
```



注入到pluginApplicationContext的代码如下：



```
1. ConfigDefinition configDefinition = configDefinitionClass.getAnnotation(ConfigDefinition.class); 

2. if(configDefinition == null){ 

3.   return NULL_REGISTER_BEAN; 

4. } 

5. String fileName = getConfigFileName(configDefinition); 

6. Object parseObject; 

7. if(fileName == NULL_CONFIG_FILE_NAME){ 

8.   parseObject = configDefinitionClass.newInstance(); 

9. }else{ 

10.   PluginConfigDefinition pluginConfigDefinition = new PluginConfigDefinition(fileName,configDefinitionClass); 

11.   parseObject = configurationParser.parse(pluginRegistryInfo,pluginConfigDefinition); 

12. } 

13.  

14. String beanName = configDefinition.beanName(); 

15. if(StringUtils.isNull(beanName)){ 

16.   beanName = configDefinitionClass.getName(); 

17. } 

18. beanName = beanName.concat("@").concat(pluginRegistryInfo.getPluginWrapper().getPluginId()); 

19. // 注册到插件的Spring上下文中 

20.super.registerSingleton(beanName,pluginRegistryInfo,parseObject); 

21. // 注册到插件信息中 

22. pluginRegistryInfo.addConfigFileObject(parseObject); 

23. return beanName; 
```



yaml读取成对象到此结束。



#### **5、lambda函数**



在springboot-plugin中有很多方法的参数是lambda函数，如果使用传统方法的话代码会繁杂和冗余，而使用lambda函数则显得很优雅



##### （1）Supplier



在第4节中将plugin.yml读取成对象的前提是找到plugin.yml并将它变成Resource以供下一步的解析操作。

而这个查找操作是有多种方式的，比如从插件配置目录、插件classPath中、插件的根目录下等等。

这个地方设计是可以采用Supplier的，只要一个方式返回了Resource，即认为找到plugin.yml文件。



相关代码如下：



```
1. @Override 

2. public ResourceWrapper load(PluginRegistryInfo pluginRegistryInfo){ 

3.  

4.   List<Supplier<Resource>> resolveResources = Lists.newArrayList(); 

5.   // 想方设法的加载fileName配置文件 

6.   resolveResources.add(findInPluginConfigPath()); 

7.   resolveResources.add(findInPluginPath(pluginRegistryInfo)); 

8.   resolveResources.add(findInPluginClassPath(pluginRegistryInfo)); 

9.  

10.   for (Supplier<Resource> resourceSupplier : resolveResources) { 

11.     Resource resource = resourceSupplier.get(); 

12.     if (resource.exists()) { 

13.       List<Resource> pluginResource = Lists.newArrayList(resource); 

14.       ResourceWrapper resourceWrapper = new ResourceWrapper(); 

15.       resourceWrapper.addResources(pluginResource); 

16.       return resourceWrapper; 

17.     } 

18.   } 

19.  

20.   throw new PluginContextRuntimeException("找不到指定的插件配置文件：[" + fileName + "]"); 

21. } 
```



从插件配置目录下查找：



```
1. /** 

2. * 直接从传入的pluginConfigPath目录下查找fileName文件 

3. * 

4. * @return 

5. */ 

6. private Supplier<Resource> findInPluginConfigPath() { 

7.   return () -> { 

8.     String filePath = pluginConfigPath + File.separator + fileName; 

9.     Resource resource = new FileSystemResource(filePath); 

10.     return resource; 

11.   }; 

12. } 
```



从插件根目录下查找：



```
1. /** 

2. * 从加载的插件根目录下查找fileName文件 

3. * 

4. * @return 

5. */ 

6. private Supplier<Resource> findInPluginPath(PluginRegistryInfo pluginRegistryInfo) { 

7.   return () -> { 

8.     BasePlugin basePlugin = pluginRegistryInfo.getBasePlugin(); 

9.     Path pluginPath = basePlugin.getWrapper().getPluginPath(); 

10.     String rootPath = pluginPath.getParent().toString(); 

11.     String filePath = rootPath + File.separator + fileName; 

12.     Resource resource = new FileSystemResource(filePath); 

13.     return resource; 

14.   }; 

15. } 
```



从插件classPath下查找：



```
1. /** 

2. * 从插件的运行环境下的 

3. * 

4. * @return 

5. */ 

6. private Supplier<Resource> findInPluginClassPath(PluginRegistryInfo pluginRegistryInfo) { 

7. return () -> {
  ClassLoader pluginClassLoader = pluginRegistryInfo.getDefaultPluginClassLoader();
  Resource resource = new ClassPathResource("/" + fileName, pluginClassLoader);
  return resource;
}; 	

8. } 
```



##### （2）Function



对插件初始化的时候会经过一些PluginPreProcessor进行处理，而这些PluginPreProcessor加载和处理是有顺序的，这个顺序是由OrderPriority决定的



```
1. public interface PluginPreProcessor { 

2.  

3.   /** 

4.   * 优先级 

5.   * 

6.   * @return 

7.   */ 

8.   default OrderPriority order(){ 

9.     return OrderPriority.getMiddlePriority(); 

10.   } 

11. } 
```



我们在执行这些PluginPreProcessor的时候会对它们排序，而这个排序工具类方法则需要将PluginPreProcessor转换成OrderPriority进行处理，这个时候用Function完成转换对代码设计来说是很优雅的



```
1. public static <T> Comparator<T> orderPriority(final Function<T, OrderPriority> order){ 

2.      return Comparator.comparing(t -> {

3.       OrderPriority orderPriority = order.apply(t);

4.       if(orderPriority == null){

5.         orderPriority = OrderPriority.getLowPriority();

6.       }

7.       return orderPriority.getPriority();

8.     }, Comparator.nullsLast(Comparator.reverseOrder()));

9. } 
```



##### （3）Consumer



在向pluginApplicationContext中装配beanDefinition之前，有的时候还需要对beandefinition做一些额外的处理，而这种处理如果用代码来实现的话会非常冗余，这个时候不妨使用一个Consumer来对beanDefinition做最后的处理



```
1. protected String register(String beanName,GenericApplicationContext pluginApplicationContext, AnnotatedGenericBeanDefinition beanDefinition, Consumer<AnnotatedGenericBeanDefinition> beanDefinitionConsumer){ 

2.  

3.   Objects.requireNonNull(beanName,"bean名称不能为空"); 

4.  

5.   if(pluginApplicationContext.containsBean(beanName)){ 

6.     log.error("插件 spring环境中注册bean [{}] 失败：禁止重复注册",beanName ); 

7.     return beanName; 

8.   } 

9.  

10.   if(beanDefinitionConsumer != null) { 

11.     beanDefinitionConsumer.accept(beanDefinition); 

12.   } 

13.  

14.   pluginApplicationContext.registerBeanDefinition(beanName,beanDefinition); 

15.   return beanName; 

16. } 
```



lambda函数结束。



#### **6、Swagger实时更新**



**关键字：DocumentationPluginsBootstrapper**



在springboot-plugin中有个需求：对插件进行启用或者禁用的时候都需要对Swagger文档进行更新

实现思路就是创建个插件事件监听器，在发生启用或者禁用事件的时候去refresh Swagger的上下文



相关实现代码如下：



```
1. public class SwaggerRefreshPluginListener implements PluginListener { 

2.  

3.   private final ApplicationContext mainApplicationContext; 

4.  

5.   public SwaggerRefreshPluginListener(ApplicationContext mainApplicationContext) { 

6.     this.mainApplicationContext = mainApplicationContext; 

7.   } 

8.  

9.   /** 

10.   * 监听插件的注册事件 

11.   * 

12.   * @param pluginId 插件Id 

13.   * @param isStartInitial 是否是插件初次初始化时的注册事件 

14.   */ 

15.   @Override 

16.   public void registry(String pluginId, boolean isStartInitial) { 

17.     if(isStartInitial){ 

18.       return; 

19.     } 

20.     refresh(); 

21.   } 

22.  

23.   /** 

24.   * 监听插件的注销事件 

25.   * 

26.   * @param pluginId 

27.   */ 

28.   @Override 

29.   public void unRegistry(String pluginId) { 

30.     refresh(); 

31.   } 

32.  

33.  

34.   /** 

35.   * 刷新Swagger的上下文 

36.   */ 

37.   private void refresh(){ 

38.     DocumentationPluginsBootstrapper documentationPluginsBootstrapper = mainApplicationContext.getBean(DocumentationPluginsBootstrapper.class); 

39.     try { 

40.       if(documentationPluginsBootstrapper != null){ 

41.         documentationPluginsBootstrapper.stop(); 

42.         documentationPluginsBootstrapper.start(); 

43.       } 

44.     } catch (Exception e) { 

45.       e.printStackTrace(); 

46.       log.error("swagget api实时更新失败：[{}]",e.getMessage(),e); 

47.     } 

48.   } 

49.  

50. } 
```



Swagger实时更新结束。



#### **7、Spring Doc实时更新**



**关键字：AbstractOpenApiResource、OpenAPIService**

工具类： ClassUtils



在springboot-plugin中有个需求：对插件进行启用或者禁用的时候都需要对Spring Doc文档进行更新。

实现思路和Swagger不同，Spring Doc更多的是针对Controller层的变换，当发生Controller的变换时才需要进行上下文的刷新。



相关代码如下：



```
1. public class SpringDocControllerProcessorExtension implements PluginControllerExtension { 

2.  

3.   private final ApplicationContext applicationContext; 

4.  

5.   private List<Class<?>> restControllers; 

6.   privateOpenAPIService openAPIService; 

7.  

8.   public SpringDocControllerProcessorExtension(ApplicationContext applicationContext) { 

9.     this.applicationContext = applicationContext; 

10.   } 

11.  

12.   @Override 

13.   public void initialize() { 

14.      AbstractOpenApiResource openApiResource = applicationContext.getBean(AbstractOpenApiResource.class);

15.     if(openApiResource == null){

16.       return;

17.     }

18.     try {

19.       restControllers = (List<Class<?>>)ClassUtils.getReflectionFiled(openApiResource,"ADDITIONAL_REST_CONTROLLERS");

20.     } catch (IllegalAccessException e) {

21.       restControllers = null;

22.     }

23.     openAPIService = applicationContext.getBean(OpenAPIService.class);

24.   } 

25.  

26.   @Override 

27.   public void registry(String pluginId, List<ControllerWrapper> controllerWrappers) throws Exception { 

28.     if(restControllers != null){ 

29.       controllerWrappers.forEach(controllerWrapper -> restControllers.add(controllerWrapper.getBeanClass())); 

30.       this.refresh(); 

31.     } 

32.   } 

33.  

34.   @Override 

35.   public void unRegistry(String pluginId, List<ControllerWrapper> controllerWrappers) throws Exception { 

36.     if(restControllers != null){ 

37.       controllerWrappers.forEach(controllerWrapper -> restControllers.remove(controllerWrapper.getBeanClass())); 

38.       this.refresh(); 

39.     } 

40.   } 

41.  

42.   /** 

43.   * 刷新springDoc上下文 

44.   */ 

45.   private void refresh(){ 

46.     if(openAPIService != null){ 

47.       openAPIService.setCachedOpenAPI(null); 

48.       openAPIService.resetCalculatedOpenAPI(); 

49.     } 

50.   } 

51. } 
```



Spring Doc实时更新结束。



#### **8、Thymeleaf扩展**



在springboot-plugin中有个需求：让插件支持thymeleaf功能，也就是插件中thymeleaf可以被正常的解析和访问。

对于Thymeleaf，类似于Freemarker，如果需要它正确识别出你需要访问的资源，需要TemplateEngine根据ITemplateResolver 去解析用户需要访问的资源。

对于TemplateEngine，我们可以直接从主版本中提取，我们需要自定义ItemplateResolver解析规则，然后将它注册到TemplateEngine中。



在插件初始化的时候：



```
1. public void registry(PluginRegistryInfo pluginRegistryInfo) throws Exception { 

2.   SpringTemplateEngine springTemplateEngine = getSpringTemplateEngine(pluginRegistryInfo); 

3.   if(springTemplateEngine == null){ 

4.     return; 

5.   } 

6.   SpringBootThymeleafConfig springBootThymeleafConfig = getThymeleafConfig(pluginRegistryInfo); 

7.   if(springBootThymeleafConfig == null){ 

8.     return; 

9.   } 

10.   ThymeleafConfig thymeleafConfig = new ThymeleafConfig(); 

11.   springBootThymeleafConfig.config(thymeleafConfig); 

12.   // 校验用户自定义的thymeleafConfig 

13.   verifyThymeleafConfig(thymeleafConfig); 

14.  

15.   ClassLoader pluginClassLoader = pluginRegistryInfo.getDefaultPluginClassLoader(); 

16.   ClassLoaderTemplateResolver templateResolver =newClassLoaderTemplateResolver(pluginClassLoader); 

17.  

18.   // 配置资源解析规则 

19.   templateResolver.setCacheable(thymeleafConfig.isCache()); 

20.   templateResolver.setPrefix(thymeleafConfig.getPrefix()); 

21.   templateResolver.setSuffix(thymeleafConfig.getSuffix()); 

22.   templateResolver.setTemplateMode(thymeleafConfig.getMode()); 

23.   if(thymeleafConfig.getEncoding() != null){ 

24.     templateResolver.setCharacterEncoding(thymeleafConfig.getEncoding().name()); 

25.   } 

26.   if(thymeleafConfig.getTemplateResolverOrder() != null){ 

27.     templateResolver.setOrder(thymeleafConfig.getTemplateResolverOrder()); 

28.   } 

29.   templateResolver.setCheckExistence(true); 

30.  

31.   springTemplateEngine.addTemplateResolver(templateResolver); 

32.  

33.   pluginRegistryInfo.addExtension(PLUGIN_THYMELEAF_TEMPLATE_RESOLVER_KEY,templateResolver); 

34. } 
```



当插件禁用的时候：



```
1. @Override 

2. public void unRegistry(PluginRegistryInfo pluginRegistryInfo) throws Exception { 

3.  

4.   ClassLoaderTemplateResolver templateResolver = (ClassLoaderTemplateResolver)pluginRegistryInfo.getExtension(PLUGIN_THYMELEAF_TEMPLATE_RESOLVER_KEY); 

5.   if(templateResolver == null){ 

6.     return; 

7.   } 

8.   SpringTemplateEngine springTemplateEngine = getSpringTemplateEngine(pluginRegistryInfo); 

9.   Set<ITemplateResolver> springTemplateResolvers = getSpringTemplateResolvers(springTemplateEngine); 

10.   if(springTemplateResolvers != null){ 

11.     springTemplateResolvers.remove(templateResolver); 

12.   } 

13. } 
```



Thymeleaf扩展结束。