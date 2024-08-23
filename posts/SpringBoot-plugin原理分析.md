SpringBoot-plugin原理分析
2024-08-22
SpringBoot-plugin插件化目标在于SpringBoot项目上开发出用于扩展项目的插件，实现在原有项目基础上集成动态的功能模块，框架实现的功能可以类比Java SPI机制。
01.jpg
源码解读
huizhang43

#### **1、什么是插件化？**



##### （1） 插件化定义



插件化目标在于SpringBoot项目上开发出用于扩展项目的插件，实现在原有项目基础上集成动态的功能模块。

框架实现的功能可以类比Java SPI机制。



##### （2） 插件化模块



在下面介绍插件化框架的过程中，我们划分成三个模块，分别是**主版本**、**插件版本**和**插件扩展**。它们三者关系如下：



![img](http://pcc.huitogo.club/57d6dce63717b3867b63d82da2764b47)



##### （3） 插件化支持功能



我们的框架是基于以下项目：



https://gitee.com/starblues/springboot-plugin-framework-parent/tree/2.4.0/



所以支持的功能也是类似的：



1）在springboot上可以进行插件式开发, 扩展性极强, 可以针对不同项目开发不同插件, 进行不同插件jar包的部署。

2）无需重启主程序, 动态的启用插件、停止插件。

3）在插件应用模块上可以使用Spring注解定义组件, 进行依赖注入。

4）支持在插件中开发Rest接口。

5）支持自定义扩展开发接口, 使用者可以在预留接口上扩展额外功能。

6）支持插件之间的通信。

7）支持插件接口文档: Swagger、SpringDoc。



#### **2、插件化怎么使用？**



入门使用可以参考原框架文档：



https://gitee.com/starblues/springboot-plugin-framework-parent/wikis/pages?sort_id=1693478&doc_id=343010



#### **3、插件化的原理是什么？**



##### **（1）插件和主版本**



首先从Spring容器的角度来看一下主版本和插件版本的Resource装配过程，简图如下：



![img](http://pcc.huitogo.club/9f65c0403334340a2ae32a626bd0dcfc)



所以，我们可以看出



1） 对于主版本，它是由SpringBoot自动装配的，并会将最终解析的结果（包括bean和configuration）放到mainApplicationContext中，所以这一步我们是不需要考虑的。

2） 对于插件版本，它的pluginApplicationContext需要我们主动去填充，比如bean和configuration，你可以把这个pluginApplicationContext想象成一个空房间，它里面有什么取决于我们往里面放什么。所以这个是我们插件化主要考虑的内容。

3） 对于插件版本和主版本之间的交互过程，因为在我们的框架设计中，mainApplicationContext和pluginApplicationContext是相互独立的spring上下文，但是在有的场景，比如插件中RequestMappingInfo（Controller的Mapping映射）， 是需要放到主版本的HandlerMapping中，从而实现插件的Controller层可以被Http访问的。



##### **（2）插件生命周期**



其次我们简单的分析插件版本的生命周期，下图所示



![img](http://pcc.huitogo.club/d23257df1e0cec4fcd4383e97590dc09)



其中各个阶段的解释：



1） init

插件版本程序初始化。



2） plugin registry

启动插件版本。



3） 解析Resource

对插件版本中的Resource进行解析，在dev环境下是target/下的文件，在deploy环境下是jar包中的文件，其中解析的内容大致分为class文件和配置文件（.resource文件和.yaml文件）



4） Resource分类

对上一步解析出来的Class类进行分组，分组的目的是用于下一步装配Resource时针对不同的Class分组进行不同的装配过程，目前框架中将Class分为Caller、Supplier、Component、ConfigBean、ConfigDefinition、Controller、OneselfListener、Repository。



5） 装配Resource

将上一步不同分组的Class类装配到插件版本的pluginApplicationContext，也就是插件的Spring上下文中。



6） plugin unRegistry

停止插件版本。



7） 释放Resource

这个阶段发生于用户动态的停止插件的过程，用于移除插件在程序中的缓存Resource。



8） destroy

插件版本程序关闭，这一部分暂时没有设计。



##### **（3）插件源码分析**



最后我们从源码的角度看一下插件生命周期的实现过程



在主版本中



```
1. @Configuration 

2. public class PluginBeanConfig { 

3.  

4.   @Bean 

5.   public PluginApplication pluginApplication() { 

6.     PluginApplication pluginApplication = new AutowiredPluginApplication(); 

7.     return pluginApplication; 

8.   } 

9. } 
```



在插件化版本中



```
1. public class AutowiredPluginApplication extends DefaultPluginApplication implements PluginApplication, ApplicationContextAware, InitializingBean { 

2.  

3.   private ApplicationContext applicationContext; 

4.   private PluginInitializerListener pluginInitializerListener; 

5.  

6.   @Override 

7.   public void setApplicationContext(ApplicationContext applicationContext) throws BeansException { 

8.     this.applicationContext = applicationContext; 

9.   } 

10.  

11.   @Override 

12.   public void afterPropertiesSet() throws Exception { 

13.     super.initialize(applicationContext,pluginInitializerListener); 

14.   } 

15.  

16.   public void setPluginInitializerListener(PluginInitializerListener pluginInitializerListener) { 

17.     this.pluginInitializerListener = pluginInitializerListener; 

18.   } 

19. } 
```



插件版本是借助InitializingBean随主版本启动而初始化的，核心是调用了PluginApplication.Initialize方法，如下：



```
1. @Override 

2. public void initialize(ApplicationContext applicationContext, PluginInitializerListener listener) { 

3.   Objects.requireNonNull(applicationContext,"参数 [applicationContext] 不能为空"); 

4.  // 判断当前插件环境是否已经初始化了

5.   if(isInitial.get()){ 

6.     throw new MainContextRuntimeException("主版本已经初始化，不要重复初始化"); 

7.   } 

8.  

9.   // 获取主版本对插件的配置 

10.   IntegrationConfiguration configuration = getConfiguration(applicationContext); 

11.   if(pf4jApplicationContext == null) { 

12.     pf4jApplicationContext = new DefaultPf4jApplicationContext(configuration); 

13.   } 

14.    

15.   PluginManager pluginManager = pf4jApplicationContext.getPluginManager(); 

16.   pluginOperator = createPluginOperator(applicationContext,pluginManager,configuration); 

17.  

18.   try { 

19.     // 插件初始化（核心） 

20.     pluginOperator.initPlugins(listener); 

21.   } catch (Exception e) { 

22.     throw new PluginContextRuntimeException("插件初始化异常：[" +e.getMessage()+ "]",e); 

23.   } 

24.  

25.   isInitial.set(true); 

26. } 
```



在解释以上的插件初始化流程之前，我们要先了解一下**pf4j**，以下是官方文档地址：



https://github.com/pf4j/pf4j



借助官方对它的一段介绍：



```
1. A plugin is a way for a third party to extend the functionality of an application. A plugin implements extension points declared by application or other plugins. Also a plugin can define extension points. 
```



简单来说就是一个开源的Java Plugin Framework，我们开发的框架也是基于它去实现的。在pf4j中有4个重要组件，也在我们插件初始化流程中起到重要作用：



###### 1） Plugin



最基本的插件组件，是我们开发插件版本的实体代表。



```
1. Plugin is the base class for all plugins types. Each plugin is loaded into a separate class loader to avoid conflicts 
```



###### 2） PluginWrapper



对Plugin的包装类，从中可以拿到一个插件的很多信息，比如PluginClassLoader和PluginManager，可以理解成一个工具类。



###### 3） PluginClassLoader



插件环境的类加载器，用来加载插件中的所有Resource。



```
1. PluginLoader loads all information (classes) needed by a plugin 
```



###### 4） PluginManager



针对所有插件的插件管理器，除了对所有PluginWrapper的操作外，还包括重要的对插件生命周期的功能。



```
1. PluginManager is used for all aspects of plugins management (loading, starting, stopping). You can use a builtin implementation as JarPluginManager, ZipPluginManager, DefaultPluginManager (it's a JarPluginManager + ZipPluginManager) or you can implement a custom plugin manager starting from AbstractPluginManager (implement only factory methods) 
```

在介绍完pf4j之后，再回到PluginApplication. Initialize方法中来，我们根据当前的插件运行环境（ dev和deploy）构建了自定义的PluginManager



```
1. // 开发环境下的插件配置 

2. if (RuntimeMode.DEVELOPMENT == environment) { 

3.   Path path = Paths.get(getDevPluginDir(integrationConfiguration)); 

4.   return createDevPluginManager(path, sortedPluginIds); 

5. } else { 

6.   Path path = Paths.get(getProdPluginDir(integrationConfiguration)); 

7.   return createProdPluginManager(path, sortedPluginIds); 

8. } 
```



而在构建PluginManager过程中，这里以dev环境为例



```
1. private PluginManager createDevPluginManager(Path devPath, List<String> sortedPluginIds){ 

2.   return new DefaultPluginManager(devPath) { 

3.  

4.     @Override 

5.     protected void initialize() { 

6.       super.initialize(); 

7.       dependencyResolver = new SortDependencyResolver(sortedPluginIds,versionManager); 

8.     } 

9.  

10.     // 设置当前插件的运行模式 

11.     @Override 

12.     public RuntimeMode getRuntimeMode() { 

13.       System.setProperty("pf4j.mode", RuntimeMode.DEVELOPMENT.toString()); 

14.       return RuntimeMode.DEVELOPMENT; 

15.     } 

16.  

17.     // PluginDescriptorFinder：根据插件版本中的plugin.resources文件读取Plugin信息 

18.     @Override 

19.     protected PluginDescriptorFinder createPluginDescriptorFinder() { 

20.       return DefaultPf4jApplicationContext.getPluginDescriptorFinder(RuntimeMode.DEVELOPMENT); 

21.     } 

22.  

23.     //PluginStatusProvider：判断哪些插件是启用，哪些插件是禁用 

24.     @Override 

25.     protected PluginStatusProvider createPluginStatusProvider() { 

26.       return new ConfigPluginStatusProvider( 

27.           integrationConfiguration.enablePluginIds(), 

28.           integrationConfiguration.disablePluginIds()); 

29.     } 

30.  

31.     //PluginLoader：插件类信息加载器 

32.     @Override 

33.     protected PluginLoader createPluginLoader() { 

34.       return new CompoundPluginLoader() 

35.           .add(new DevelopmentPluginLoader(this),this::isDevelopment); 

36.     } 

37.  

38.   }; 

39. } 
```



我们为PluginManager配置了一些可以用来正确读取Plugin信息的功能，配置好PluginManager之后就是插件初始化过程中最重要的一个方法PluginOperator.initPlugins



```
1. public synchronized boolean initPlugins(PluginInitializerListener pluginInitializerListener) throws Exception { 

2.   // 判断当前插件环境是否已经初始化了 

3.   if (isPluginInitial.get()) { 

4.     throw new PluginContextRuntimeException("当前插件的环境已经初始化了"); 

5.   } 

6.   pluginInitializerListenerManager.addPluginInitializerListeners(pluginInitializerListener); 

7.  

8.   try { 

9.     // 插件初始化事件监听器 开始 

10.     pluginInitializerListenerManager.before(); 

11.     if (!configuration.enable()) { 

12.       pluginInitializerListenerManager.complete(); 

13.       return false; 

14.     } 

15.     // 清理配置插件目录下的空文件（夹） 

16.     PluginFileHelper.cleanEmptyFile(pluginManager.getPluginsRoot()); 

17.     // 插件加工厂环境初始化 

18.     pluginFactory.initialize(); 

19.  

20.     // 装载插件环境信息和资源到内存中 

21.     pluginManager.loadPlugins(); 

22.     // 启动插件（更新插件状态） 

23.     pluginManager.startPlugins(); 

24.     List<PluginWrapper> pluginWrappers = pluginManager.getStartedPlugins(); 

25.     if (pluginWrappers == null || pluginWrappers.isEmpty()) {  

26.       return false; 

27.     } 

28.     // 插件在registry过程中是否出现异常 

29.     boolean ifRegistryException = false; 

30.     for (PluginWrapper pluginWrapper : pluginWrappers) { 

31.       String pluginId = pluginWrapper.getPluginId(); 

32.       // 记录插件的操作状态 

33.       addOperatorPluginInfo(pluginId, PluginOperateInfo.OperateType.INSTALL, false); 

34.  

35.       try { 

36.         // 插件加工厂 注册单个插件信息

37.         pluginFactory.registry(PluginRegistryInfo.build(pluginWrapper, pluginManager, mainApplicationContext,true)); 

38.       } catch (Exception e) { 

39.         ifRegistryException = true; 

40.       } 

41.     } 

42.     // 插件加工厂 启动前对插件的操作 

43.     pluginFactory.build(); 

44.     isPluginInitial.set(true); 

45.  

46.     if (ifRegistryException) { 

47.       return false; 

48.     } else { 

49.       // 插件初始化事件监听器 完成 

50.       pluginInitializerListenerManager.complete(); 

51.       return true; 

52.     } 

53.   } catch (Exception e) { 

54.     // 插件初始化事件监听器 异常 

55.     pluginInitializerListenerManager.failure(e); 

56.     throw new PluginContextRuntimeException("插件初始化异常:" + e.getMessage()); 

57.   } 

58. } 
```



对于以上插件初始化的过程大致可以分成三个过程：



1） 准备阶段



 pluginInitializerListenerManager.before() ：插件初始化事件监听器



 pluginFactory.initialize() : 插件环境初始化（关于PluginFactory后面再介绍）



 pluginManager.loadPlugins() ：解析插件里的配置信息，可以理解成将pluginPath路径下的带有plugin.properties配置文件的插件 转换成Plugin 放到PluginManager中



2） 注册阶段



pluginManager.startPlugins() : 启动所有插件（更新插件状态）

pluginFactory.registry() : 注册单个插件信息



3） 结束阶段



pluginFactory.build() ： 对所有插件进行构建

pluginInitializerListenerManager.complete() ：插件注册完成事件监听器



在上述步骤中，插件事件监听器和PluginManager的相关操作这里不作赘述，主要看一下PluginFactory下的initialize和registry方法



```
1. @Override 

2. public void initialize() throws Exception { 

3.   // 添加默认的插件事件监听器，可扩展 

4.   addDefaultPluginListener(); 

5.   pluginPreProcessorManager.initialize(); 

6.   pluginPostProcessorManager.initialize(); 

7. } 

8.  

9. @Override 

10. public synchronized PluginFactory registry(PluginRegistryInfo pluginRegistryInfo) throws Exception { 

11.   String pluginId = pluginRegistryInfo.getPluginWrapper().getPluginId(); 

12.   if(PluginContextHelper.getPluginRegistryInfo(pluginId) != null){ 

13.     throw new PluginContextRuntimeException("插件" + pluginId + "已经注册，无须重复注册"); 

14.   } 

15.   // 只有当插件生命周期为BUILD或者REGISTER的时候才允许注册插件 

16.   if(!buildPluginRegistryList.isEmpty() && buildType == BuildType.UNINSTALL){ 

17.     throw new PluginContextRuntimeException("插件" + pluginId + "注册失败，当前非插件的注册周期"); 

18.   } 

19.   try { 

20.     pluginPreProcessorManager.registry(pluginRegistryInfo); 

21.  

22.     PluginContextHelper.addPluginPluginRegistryInfo(pluginId,pluginRegistryInfo); 

23.     buildPluginRegistryList.add(pluginRegistryInfo); 

24.     return this; 

25.   } catch (Exception e) { 

26.     pluginListenerManager.failure(pluginId,e); 

27.     throw e; 

28.   }finally { 

29.     buildType = BuildType.REGISTER; 

30.   } 

31. } 
```



这里有两个重要的类，**PluginPreProcessorManager**和**PluginPostProcessorManager**，PluginPreProcessorManager是一堆**PluginPreProcessor**的集合，相应PluginPostProcessorManager是一堆**PluginPostProcessor**的集合。

对PluginFactory的initialize和registry其实也就是调用PluginPreProcessorManager和PluginPostProcessorManager的initialize和registry，



先看一下PluginPreProcessorManager.initialize



```
1. public void initialize(){ 

2.   // Resource加载 

3.   pluginPreProcessors.add(new PluginResourceLoaderPreProcessor()); 

4.   // Resouce分类 

5.   pluginPreProcessors.add(new PluginClassResolvePreProcessor()); 

6.   // Resource装配 

7.   pluginPreProcessors.add(new PluginApplicationContextPreProcessor(mainApplicationContext)); 

8.   // Resource 自定义Bean装配 

9.   pluginPreProcessors.add(new PluginConfigBeanPreProcessor()); 

10.  

11.   pluginPreProcessors.forEach(PluginPreProcessor::initialize); 

12. } 
```



在这里可以看到我们之前在插件生命周期中介绍的一些阶段，对于PluginPreProcessor和PluginPostProcessor的设计来说，是类似于Spring的BeanPostProcessor，Spring中的bean实例化和初始化阶段经历一系列前置器和后置器会增强，这里插件的初始化也是如此。

PluginPreProcessorManager和PluginPostProcessorManager的作用都是在插件registry或者unRegistry的时候对插件的一些操作。不同的是PluginPreProcessorManager是**针对单个插件**进行操作，而PluginPostProcessorManager是需要等 PluginPreProcessorManager执行完后**针对所有的插件**进行操作。



接下来详细介绍一下PluginPreProcessor和PluginPostProcessor的功能和它们的源码



1） PluginResourceLoaderPreProcessor：对插件Resource的加载



当有插件registry的时候，会使用所有的PluginResourceLoader从PluginRegistryInfo中加载出ResourceWrapper



```
1. @Override 

2. public void registry(PluginRegistryInfo pluginRegistryInfo) { 

3.   resourceLoaderList.forEach(resourceLoader ->{ 

4.     if(StringUtils.isNull(resourceLoader.key())){ 

5.       log.warn("插件加载器 [{}] 未配置key，直接跳过",resourceLoader.getClass().getName()); 

6.       return; 

7.     } 

8.     try { 

9.       ResourceWrapper resourceWrapper = resourceLoader.load(pluginRegistryInfo); 

10.       if(resourceWrapper != null) { 

11.         pluginRegistryInfo.addPluginLoadResource(resourceLoader.key(), resourceWrapper); 

12.       } 

13.     } catch (IOException e) { 

14.       log.error("插件加载器 [{}] 加载插件 [{}] 异常",resourceLoader.getClass().getName(),pluginRegistryInfo.getPluginWrapper().getPluginId()); 

15.     } 

16.   }); 

17. } 
```



2） PluginClassResolvePreProcessor：插件Class分类



遍历ResourceWrapper下的所有Class，在满足对应的PluginClassGroup的条件后会加入到对应的PluginClassGroup中；在Class没有匹配到任何PluginClassGroup后会进入缺省的Group。



```
1. @Override 

2. public void registry(PluginRegistryInfo pluginRegistryInfo) throws ClassNotFoundException { 

3.   BasePlugin basePlugin = pluginRegistryInfo.getBasePlugin(); 

4.   ResourceWrapper resourceWrapper = pluginRegistryInfo.getPluginLoadResource(PluginResourceLoader.DEFAULT_PLUGIN_RESOURCE_LOADER_KEY); 

5.   // 插件里没有class 

6.   if (resourceWrapper == null) { 

7.     return; 

8.   } 

9.   List<Resource> resources = resourceWrapper.getResources(); 

10.   // 插件没有配置文件（插件属性） 

11.   if (resources == null) { 

12.     return; 

13.   } 

14.  

15.   pluginClassGroups.forEach(pluginClassGroup -> { 

16.     pluginClassGroup.initialize(basePlugin); 

17.   }); 

18.  

19.   Set<String> pluginPackageClasses = resourceWrapper.getClassPackageNames(); 

20.   ClassLoader pluginClassLoader = basePlugin.getWrapper().getPluginClassLoader(); 

21.  

22.   for (String className : pluginPackageClasses) { 

23.     Class pluginClass = Class.forName(className, false, pluginClassLoader); 

24.     if (pluginClass == null) { 

25.       continue; 

26.     } 

27.     boolean isMatchGroup = false; 

28.  

29.     for (PluginClassGroup pluginClassGroup : pluginClassGroups) { 

30.       if (pluginClassGroup == null || StringUtils.isNull(pluginClassGroup.groupId())) { 

31.         return; 

32.       } 

33.       if (pluginClassGroup.filter(pluginClass)) { 

34.         pluginRegistryInfo.addClassInGroup(pluginClassGroup.groupId(), pluginClass); 

35.         isMatchGroup = true; 

36.       } 

37.     } 

38.     if(!isMatchGroup){ 

39.       pluginRegistryInfo.addClassInGroup(UNMATCH_GROUP_ID, pluginClass); 

40.     } 

41.     //添加进容器中 

42.     pluginRegistryInfo.addPluginClass(pluginClass); 

43.   } 

44.  

45.  

46. } 
```



3） PluginApplicationContextPreProcessor：插件Resource装配



简单的说就是将上述每个PluginClassGroup中的Class转换成BeanDefinition放到插件Spring上下文pluginApplicationContext中，在所有的PluginClassGroup下的Class装配完之后会对pluginApplicationContext进行refresh操作。



```
1. @Override 

2. public void registry(PluginRegistryInfo pluginRegistryInfo) throws Exception { 

3.   for(PluginBeanRegistrar pluginBeanRegistrar : pluginBeanRegistrars){ 

4.     // 对不同PluginClassGroup采用不同的装配方式 

5.     pluginBeanRegistrar.registry(pluginRegistryInfo); 

6.   } 

7.  

8.   addPluginExtension(pluginRegistryInfo); 

9.   GenericApplicationContext pluginApplicationContext = pluginRegistryInfo.getPluginApplicationContext(); 

10.  

11.   ClassLoader mainContextClassLoader = Thread.currentThread().getContextClassLoader(); 

12.   ClassLoader pluginContextClassLoader = pluginRegistryInfo.getDefaultPluginClassLoader(); 

13.  

14.   try{ 
     // 切换当前线程类加载器，用于插件Spring上下文的refresh

15.     Thread.currentThread().setContextClassLoader(pluginContextClassLoader); 

16.     // 刷新插件spring上下文环境 

17.     pluginApplicationContext.refresh(); 

18.   }finally { 

19.     Thread.currentThread().setContextClassLoader(mainContextClassLoader); 

20.   } 

21.   String pluginId = pluginRegistryInfo.getPluginWrapper().getPluginId(); 

22.   PluginContextHelper.addPluginApplicationContext(pluginId,pluginApplicationContext); 

23. } 
```



4） PluginControllerPostProcessor：对插件中Controller层的装配



首先，为什么插件的Controller类需要单独装配?

因为我们需要将插件中的RequestMappingInfo（Controller的RequestMapping）注册到主版本的HandlerMapping中，这样我们插件的Controller才能正常的通过Http访问。



在此之前，我们从插件ResourceWrapper中解析的类都是直接装配到插件的Spring上下文中，和主版本是没有什么关系的。



```
1. @Override 

2. public void registry(List<PluginRegistryInfo> pluginRegistryInfos) throws Exception { 

3.   pluginRegistryInfos.forEach(pluginRegistryInfo -> { 

4.     List<Class> groupClasses = pluginRegistryInfo.getClassesFromGroup(ControllerGroup.GROUP_ID); 

5.     if (groupClasses == null || groupClasses.isEmpty()) { 

6.       return; 

7.     } 

8.     String pluginId = pluginRegistryInfo.getPluginWrapper().getPluginId(); 

9.     List<ControllerWrapper> controllerWrapperList = Lists.newArrayList(); 

10.     for (Class controllerClass : groupClasses) { 

11.       if (controllerClass == null) { 

12.         continue; 

13.       } 

14.       // 注册当前Controller类到主版本的mvc环境中 

15.       ControllerWrapper controllerWrapper = doRegistry(pluginRegistryInfo, controllerClass); 

16.       if (controllerWrapper != null) { 

17.         controllerWrapperList.add(controllerWrapper); 

18.       } 

19.     } 

20.     pluginRegistryInfo.addControllerWrappers(controllerWrapperList); 

21.  

22.   }); 

23. } 
```



到此，其实插件的初始化流程已经完成了，现在回顾一下整个插件初始化的过程，时序图如下：



![img](http://pcc.huitogo.club/6901ac3c27c3ebb618daa8de6c24566f)



#### **4、插件扩展功能原理**



在上述插件版本初始化后，我们在此主版本的基础上可以对插件调用的功能有：



1）主版本通过Http访问插件的Controller层，在Controller中可以使用插件pluginApplicationContext中装配的bean和其他资源。

2）主版本直接使用PluginUtils类获取pluginApplicationContext从而直接调用插件中装配的bean和其他资源。



那怎么在插件中实现更多的功能呢？



比如在插件中支持数据库操作，Mybatis、MybatisPlus或者TkMybatis？

比如在插件中访问静态资源，js、css、html呢？



因此我们需要对插件功能进行扩展，同时这些扩展功能相对于插件来说应该也是可插拔的。

那什么是插件扩展功能，说白了就是向PluginApplicationContext中放入更多的东西，让它可以支持更加复杂的功能调用，比如说支持Mybatis的话，你需要将*Mapper.class解析成MapperFactoryBean放到PluginApplicationContext中，这样在调用*Mapper.class里方法时，会通过MapperFactoryBean生成MapperProxy去调用SqlSession执行sql语句。



那怎么向PluginApplicationContext中放入更多的东西呢？



通过参考插件的生命周期，如下图所示：



![img](http://pcc.huitogo.club/62f33085fb8a7706baf132076191bb2a)



 我们通过AbstractPluginExtension抽象类提供更多的Resource解析器、Resource分组器和Resource装配器，在插件的生命周期中解析更多的Resource和Resource分组，最终在装配Resource阶段为pluginApplicationContext装配更多的资源，从而支撑更多的功能。



首先看一下AbstractPluginExtension的源码：



```
1. public abstract class AbstractPluginExtension { 

2.  

3.   /** 

4.   * 扩展标识 唯一key 

5.   * 

6.   * @return 

7.   */ 

8.   public abstract String key(); 

9.  

10.  

11.   /** 

12.   * 该扩展初始化的操作 

13.   * 主要是在插件初始化阶段被调用 

14.   * 

15.   * @param mainApplicationContext 主版本ApplicationContext 

16.   * @throws Exception 初始化异常 

17.   */ 

18.   public void initialize(ApplicationContext mainApplicationContext) throws Exception{ 

19.   } 

20.  

21.   /** 

22.   * 返回插件的资源加载器 

23.   * 主要是加载插件中的某些资源，比如文件、图片等 

24.   * 

25.   * @return List PluginResourceLoader 

26.   */ 

27.   public List<PluginResourceLoader> getPluginResourceLoaders(){ 

28.     return null; 

29.   } 

30.  

31.  

32.   /** 

33.   * 返回扩展的插件中的类分组器。 

34.   * 该扩展主要是对插件中的Class文件分组，然后供 PluginPreProcessor、PluginPostProcessor 阶段使用。 

35.   * 

36.   * @param mainApplicationContext 主程序ApplicationContext 

37.   * @return List PluginClassGroup 

38.   */ 

39.   public List<PluginClassGroup> getPluginClassGroups(ApplicationContext mainApplicationContext){ 

40.     return null; 

41.   } 

42.  

43.  

44.   /** 

45.   * 返回扩展的插件前置处理者。 

46.   * 该扩展会对每一个插件进行处理 

47.   * 

48.   * @param mainApplicationContext 主程序ApplicationContext 

49.   * @return List PluginPreProcessor 

50.   */ 

51.   public List<PluginPreProcessor> getPluginPreProcessors(ApplicationContext mainApplicationContext){ 

52.     return null; 

53.   } 

54.  

55.   /** 

56.   * 返回扩展的bean定义注册者扩展 

57.   * 该扩展会对每一个插件进行处理 

58.   * 

59.   * @param mainApplicationContext 主程序ApplicationContext 

60.   * @return List PluginBeanRegistrar 

61.   */ 

62.   public List<PluginBeanRegistrar> getPluginBeanRegistrars(ApplicationContext mainApplicationContext){ 

63.     return null; 

64.   } 

65.  

66.   /** 

67.   * 返回扩展的插件后置处理者。 

68.   * 该扩展会对全部插件进行处理。 

69.   * 

70.   * @param mainApplicationContext 主程序ApplicationContext 

71.   * @return List PluginPostProcessor 

72.   */ 

73.   public List<PluginPostProcessor> getPluginPostProcessors(ApplicationContext mainApplicationContext){ 

74.     return null; 

75.   } 

76.  

77.   /** 

78.   * 返回扩展的插件后置处理者。 

79.   * 该扩展会对每一个插件进行处理 

80.   * 

81.   * @param mainApplicationContext 主程序ApplicationContext 

82.   * @return List PluginAfterPreProcessor 

83.   */ 

84.   public List<PluginAfterPreProcessor> getPluginAfterPreProcessors(ApplicationContext mainApplicationContext){ 

85.     return null; 

86.   } 

87. } 
```



我们的插件扩展功能需要继承AbstractPluginExtension，通过覆写里面的方法来实现功能扩展。下面分别介绍Mybatis扩展和静态资源扩展下对AbstractPluginExtension的继承。



##### **（1）Mybatis扩展**



```
1. public class SpringBootMybatisPluginExtension extends AbstractPluginExtension { 

2.  

3.   private static final String KEY = "springBootMabtisPluginExtension"; 

4.  

5.   private final LoadType loadType; 

6.  

7.   public SpringBootMybatisPluginExtension() { 

8.   } 

9.  

10.   @Override 

11.   public String key() { 

12.     return KEY; 

13.   } 

14.  

15.   @Override 

16.   public List<PluginClassGroup> getPluginClassGroups(ApplicationContext mainApplicationContext) { 

17.     final List<PluginClassGroup> classGroups = Lists.newArrayList(); 

18.     // Mybatis的配置类分组 

19.     classGroups.add(newMybatisConfigGroup()); 

20.     // 数据库实体类和别名分组 

21.     classGroups.add(newPluginEntityAliasGroup()); 

22.     // 数据库Mapper访问分组 

23.     classGroups.add(newPluginMapperGroup()); 

24.     return classGroups; 

25.   } 

26.  

27.   @Override 

28.   public List<PluginBeanRegistrar> getPluginBeanRegistrars(ApplicationContext mainApplicationContext) { 

29.     final List<PluginBeanRegistrar> beanRegistrars = Lists.newArrayList(); 

30.     beanRegistrars.add(newMybatisBeanRegistrar()); 

31.     return beanRegistrars; 

32.   } 

33.  

34. } 
```



可以看到Mybatis扩展增加了3个Resource分组器和1和Resource装配器

3个Resource分组器分别是Mybatis的配置类分组、数据库实体类和别名分组 和 数据库Mapper访问分组。



重点看一下Resource装配器MybatisBeanRegistrar，当插件初始化或者有新的插件启用的时候：



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

74. } 
```



这里Mybatis的装配过程中配置或生成了一个SqlSessionFactoryBean用来生成SqlSessionFactory，SqlSessionFactoryBean里的信息来源于mainApplicationContext或者插件配置中。

最后基于数据库Mapper访问分组获取插件中的*Mapper.class，将*Mapper.class转换成MapperFactoryBean注入到pluginApplicationContext中。



```
1. private void doInjectProperties(BeanDefinitionHolder holder, 

2.                 Class<?> mapperClass, 

3.                 SqlSessionFactory sqlSessionFactory, 

4.                 SqlSessionTemplate sqlSessionTemplate) { 

5.   GenericBeanDefinition beanDefinition = (GenericBeanDefinition) holder.getBeanDefinition(); 

6.   beanDefinition.getConstructorArgumentValues().addGenericArgumentValue(mapperClass); 

7.   beanDefinition.setBeanClass(org.mybatis.spring.mapper.MapperFactoryBean.class); 

8.   beanDefinition.getPropertyValues().add("addToConfig", true); 

9.   beanDefinition.getPropertyValues().add("sqlSessionFactory", sqlSessionFactory); 

10.   beanDefinition.getPropertyValues().add("sqlSessionTemplate", sqlSessionTemplate); 

11.   beanDefinition.setAutowireMode(AbstractBeanDefinition.AUTOWIRE_BY_TYPE); 

12. } 
```



##### **（2）静态资源扩展**



```
1. public class SpringBootStaticResourceExtension extends AbstractPluginExtension { 

2.  

3.   private final static String STATIC_RESOURCE_PLUGIN_EXTENSION = "staticResourcePluginExtension"; 

4.   

5.   // 静态资源访问前缀

6.   private static String pluginResourcePrefix = "static-plugin"; 

7.  

8.   /** 

9.   * 对resource资源的访问缓存，设置缓存时间为1小时 

10.   */ 

11.   private static CacheControl pluginStaticResourceCacheControl = CacheControl.maxAge(1, TimeUnit.HOURS).cachePublic(); 

12.  

13.   @Override 

14.   public String key() { 

15.     return STATIC_RESOURCE_PLUGIN_EXTENSION; 

16.   } 

17.  

18.   @Override 

19.   public void initialize(ApplicationContext mainApplicationContext) throws Exception { 

20.     List<WebMvcConfigurer> webMvcConfigurers = Lists.newArrayList(new ResourceWebMvcConfigurer()); 

21.     // webMvc的处理委托类 

22.     DelegatingWebMvcConfiguration delegatingWebMvcConfiguration = mainApplicationContext.getBean(DelegatingWebMvcConfiguration.class); 

23.     delegatingWebMvcConfiguration.setConfigurers(webMvcConfigurers); 

24.   } 

25.  

26.   @Override 

27.   public List<PluginPostProcessor> getPluginPostProcessors(ApplicationContext mainApplicationContext) { 

28.     final List<PluginPostProcessor> pluginPostProcessors = Lists.newArrayList(); 

29.     pluginPostProcessors.add(newPluginResourceResolvePostProcessor()); 

30.     return pluginPostProcessors; 

31.   } 

32.  

33.   @Override 

34.   public List<PluginAfterPreProcessor> getPluginAfterPreProcessors(ApplicationContext mainApplicationContext) { 

35.     final List<PluginAfterPreProcessor> pluginAfterPreProcessors = Lists.newArrayList(); 

36.     pluginAfterPreProcessors.add(newPluginThymeleafResourceAfterProcessor()); 

37.     return pluginAfterPreProcessors; 

38.   } 

39. } 
```



这里将静态资源扩展的功能分为两部分



###### 1） 插件准备阶段



自定义Spring MVC的拦截配置类ResourceWebMvcConfigurer。

ResourceWebMvcConfigurer拦截配置类会拦截指定的资源访问路径前缀pathPattern，然后交由PluginResourceResolver解析出Resource。



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



最后获取主版本中SpringMVC委托处理类DelegatingWebMvcConfiguration，并将我们自定义的ResourceWebMvcConfigurer 注册到DelegatingWebMvcConfiguration中。



```
1. @Override 

2. public void initialize(ApplicationContext mainApplicationContext) throws Exception { 

3.   List<WebMvcConfigurer> webMvcConfigurers = Lists.newArrayList(new ResourceWebMvcConfigurer()); 

4.   // webMvc的处理委托类 

5.   DelegatingWebMvcConfiguration delegatingWebMvcConfiguration = mainApplicationContext.getBean(DelegatingWebMvcConfiguration.class); 

6.   delegatingWebMvcConfiguration.setConfigurers(webMvcConfigurers); 

7. } 
```



###### 2） 插件registry阶段



```
1. @Override 

2. public void registry(List<PluginRegistryInfo> pluginRegistryInfos) throws Exception { 

3.     for(PluginRegistryInfo pluginRegistryInfo : pluginRegistryInfos){

4. 

5.       List<Object> configFileObjects = pluginRegistryInfo.getConfigFileObjects();

6.       SpringBootStaticResourceConfig staticResourceConfig = null;

7. 

8.       for(Object configFileObject : configFileObjects){

9.         Class<?>[] interfaces = configFileObject.getClass().getInterfaces();

10.         if(interfaces.length > 0 && Arrays.asList(interfaces).contains(SpringBootStaticResourceConfig.class)){

11.           staticResourceConfig = (SpringBootStaticResourceConfig) configFileObject;

12.         }

13.       }

14. 

15.       if(staticResourceConfig == null){

16.         continue;

17.       }

18. 

19.       PluginResourceResolver.parse(pluginRegistryInfo,staticResourceConfig);

20.     }   

21. }
```



当插件初始化或者插件启用的时候，首先会读取插件版本中对静态资源的相关配置，比如资源的保存路径；其次会分别从ClassPath和File两个维度去读取指定路径下的Resource信息并保存在本地。

最后当我们在插件准备阶段定义的WebMvcConfigurer拦截到用户的访问请求时，直接从本地查找对应的Resource信息。



#### **5、主版本修改了什么部分？**



截止到目前为止，作为我们正在使用的主线版本基于以上框架作出了4处修改：



##### **（1）删除pluginApplicationContext**



```
1. public String register(String pluginId, Class<?> aClass, 

2.            Consumer<AnnotatedGenericBeanDefinition> consumer) { 

3.        AnnotatedGenericBeanDefinition beanDefinition = new

4.         AnnotatedGenericBeanDefinition(aClass);

5. 

6.     BeanNameGenerator beanNameGenerator =

7.         new AnnotationBeanNameGenerator();

8.     String beanName = beanNameGenerator.generateBeanName(beanDefinition, applicationContext);

9.     if(PluginInfoContainer.existRegisterBeanName((beanName))){

10.       String error = MessageFormat.format("Bean name {0} already exist of {1}",

11.           beanName, aClass.getName());

12.       logger.debug(error);

13.       return beanName;

14.     }

15.     if(consumer != null){

16.       consumer.accept(beanDefinition);

17.     }

18.     applicationContext.registerBeanDefinition(beanName, beanDefinition);

19.     PluginInfoContainer.addRegisterBeanName(pluginId, beanName);

20.     return beanName;

21. } 
```



其中applicaitonContext是mainApplicationContext，也就是说插件中解析出的所有Bean全部装配到主版本的Spring上下文中。

这在无形于解决了插件中事务的问题，在原始框架中插件是不支持事务的，因为插件中没有事务管理器，更不会为对象生成代理类去实现事务。



##### **（2）增加PluginMapper分组类**



在解析被PluginMapper注解的Mapper类后会放到主版本的ApplicationContext中，覆盖原有的Mapper。



```
1. public class PluginMapperGroup implements PluginClassGroupExtend { 

2.  

3.   public static final String GROUP_ID = "plugin_mybatis_mapper"; 

4.  

5.   @Override 

6.   public String groupId() { 

7.     return GROUP_ID; 

8.   } 

9.  

10.   @Override 

11.   public void initialize(BasePlugin basePlugin) { 

12.  

13.   } 

14.  

15.   @Override 

16.   public boolean filter(Class<?> aClass) { 

17.     return AnnotationsUtils.haveAnnotations(aClass, false, PluginMapper.class, Mapper.class); 

18.   } 

19. } 
```



##### **（3）tkMybatis 直接用主线SqlSessionFactory中的Configuration**



对于tkMybatis构建的SqlSessionFactoryBean中关于Mybatis的配置Configuration直接从主版本的SqlSessionFactory中获取。



```
1. public Configuration getConfiguration(SpringBootMybatisExtension.Type type){ 

2.   if(type == SpringBootMybatisExtension.Type.TK_MYBATIS){ 

3.     SqlSessionFactory sqlSessionFactory = applicationContext.getBean(SqlSessionFactory.class); 

4.     configuration = sqlSessionFactory.getConfiguration(); 

5.   } 

6.   return configuration; 

7. } 
```