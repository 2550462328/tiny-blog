SpringBoot自动配置原理
2024-08-22
Spring Boot 自动配置原理是利用条件注解和自动配置类。它在启动时扫描类路径，根据特定条件判断是否需要加载相应配置。通过读取配置文件和依赖中的元数据，自动配置相关组件，极大地简化了开发过程，提高了开发效率。
03.jpg
实践原理
huizhang43

#### 1. SpringBoot启动类

当SpringBoot应用启动的时候，就从主方法里面进行启动的

```
1. @SpringBootApplication 

2. public class SpringBoot02ConfigAutoconfigApplication { 

3.  

4.   public static void main(String[] args) { 

5.     SpringApplication.run(SpringBoot02ConfigAutoconfigApplication.class, args); 

6.   } 

7. } 
```



它主要加载了@SpringBootApplication注解主配置类，这个@SpringBootApplication注解主配置类里边最主要的功能就是SpringBoot开启了一个@EnableAutoConfiguration注解的自动配置功能。



#### 2. @EnableAutoConfiguration的作用

它主要利用了一个EnableAutoConfigurationImportSelector选择器给Spring容器中来导入一些组件。

```
1. @Import(EnableAutoConfigurationImportSelector.class) 

2. public @interface EnableAutoConfiguration  
```



#### 3. 那么导入了哪些组件呢？

我们来看EnableAutoConfigurationImportSelector这个类的父类AutoConfigurationImportSelector



这个类规定了一个方法叫selectImports这个方法，查看了selectImports这个方法里面的代码内容就能知道导入了哪些组件了。

```
1. public String[] selectImports(AnnotationMetadata annotationMetadata) { 

2.   if (!this.isEnabled(annotationMetadata)) { 

3.     return NO_IMPORTS; 

4.   } else { 

5.     try { 

6.       ... 

7.       List<String> configurations = this.getCandidateConfigurations(annotationMetadata, attributes); 

8.       ... 

9.     } catch (IOException var6) { 

10.       throw new IllegalStateException(var6); 

11.     } 

12.   } 

13. } 

14.  

15. protected List<String> getCandidateConfigurations(AnnotationMetadata metadata, AnnotationAttributes attributes) { 

16.   List<String> configurations = SpringFactoriesLoader.loadFactoryNames(this.getSpringFactoriesLoaderFactoryClass(), this.getBeanClassLoader()); 

17.  ... 

18. } 
```

- 方法中的getCandidateConfigurations方法，其返回一个自动配置类的类名列表



#### 4. 那么会得到什么资源？

它是扫描java jar包类路径下的“META-INF/spring.factories”这个文件

```
1. /** 

2. * The location to look for factories. 

3. * <p>Can be present in multiple JAR files. 

4. */ 

5. public static final String FACTORIES_RESOURCE_LOCATION = "META-INF/spring.factories"; 
```



**那么扫描到的这些文件作用**：是把这个文件的urls拿到之后并把这些urls每一个遍历，最终把这些文件整成一个properties对象

```
1. public static List<String> loadFactoryNames(Class<?> factoryClass, ClassLoader classLoader) { 

2.   String factoryClassName = factoryClass.getName(); 

3.   try { 

4.     Enumeration<URL> urls = (classLoader != null ? classLoader.getResources(FACTORIES_RESOURCE_LOCATION) : 

5.         ClassLoader.getSystemResources(FACTORIES_RESOURCE_LOCATION)); 

6.     List<String> result = new ArrayList<String>(); 

7.     while (urls.hasMoreElements()) { 

8.       URL url = urls.nextElement(); 

9.       Properties properties = PropertiesLoaderUtils.loadProperties(new UrlResource(url)); 

10.       String factoryClassNames = properties.getProperty(factoryClassName); 

11.       result.addAll(Arrays.asList(StringUtils.commaDelimitedListToStringArray(factoryClassNames))); 

12.     } 

13.     return result; 

14.   } 

15.     ... 

16. } 
```



它是将文件下的指定factoryClassName相关的值放到List<String>中去并返回。



我们先看一下这个spring.factories文件长啥样

![img](http://pcc.huitogo.club/0fd1c8425fc1b82ef65b5ea085a2454a)



相当于一个属性文件，那么loadFactoryNames方法是根据哪个factoryClassName获取它的值呢？

```
1. protected Class<?> getSpringFactoriesLoaderFactoryClass() { 

2.   return EnableAutoConfiguration.class; 

3. } 
```



所以，**@EnableAutoConfiguration的目的就是将META-INF/spring.factories中跟org.springframework.boot.autoconfigure.EnableAutoConfiguration有关的类注入到Spring容器中。**

 其内部实现的关键点有

- ImportSelector 该接口的方法的返回值都会被纳入到spring容器管理中
- SpringFactoriesLoader 该类可以从classpath中搜索所有META-INF/spring.factories配置文件，并读取配置



最后我们容器中会添加很多类，比如

![img](http://pcc.huitogo.club/a157d1ae277f35cedb76cabb9476bffa)



#### 5. 添加很多类到容器中是为了什么？

加入到容器中之后的作用就是**用它们来做自动配置**，这就是Springboot自动配置之源，也就是自动配置的开始，只有这些自动配置类进入到容器中以后，接下来这个自动配置类才开始进行启动。



#### 6. 那什么是自动配置？

简单说

![img](http://pcc.huitogo.club/d0819ccbe118f5c09c0e0e860f319fec)



就是这些配置文件怎么生效的！为什么你不用写配置文件或者配置代码了，因为人家SprintBoot自动给你配置了，懂了没？就是将这些配置文件里面的选项变成一个个Bean被我们所用。



#### 7. 如何自动配置

终于回到了我们的主题



这就是题5的答案，借助通过@EnableAutoConfiguration注入过来的那么多的类。我们随便打开一个文件看看它是怎么做的吧



比如我们常见的MybatisAutoConfiguration

```
@org.springframework.context.annotation.Configuration
@ConditionalOnClass({SqlSessionFactory.class, SqlSessionFactoryBean.class})
@ConditionalOnBean({DataSource.class})
@EnableConfigurationProperties({MybatisProperties.class})
@AutoConfigureAfter({DataSourceAutoConfiguration.class})
public class MybatisAutoConfiguration
{
  private static final Logger logger = LoggerFactory.getLogger(MybatisAutoConfiguration.class);
  private final MybatisProperties properties;
  private final Interceptor[] interceptors;
  private final ResourceLoader resourceLoader;
  private final DatabaseIdProvider databaseIdProvider;
  private final List<ConfigurationCustomizer> configurationCustomizers;
```

- @Spring的Configuration是一个通过注解标注的springBean，
- @ConditionalOnClass({ SqlSessionFactory.class, SqlSessionFactoryBean.class})这个注解的意思是：当存在SqlSessionFactory.class, SqlSessionFactoryBean.class这两个类时才解析MybatisAutoConfiguration配置类,否则不解析这一个配置类。我们需要mybatis为我们返回会话对象，就必须有会话工厂相关类
- @CondtionalOnBean(DataSource.class):只有处理已经被声明为bean的dataSource
- @ConditionalOnMissingBean(MapperFactoryBean.class)这个注解的意思是如果容器中不存在name指定的bean则创建bean注入，否则不执行



以上配置可以保证sqlSessionFactory、sqlSessionTemplate、dataSource等mybatis所需的组件均可被自动配置，@Configuration注解已经提供了Spring的上下文环境，所以以上组件的配置方式与Spring启动时通过mybatis.xml文件进行配置起到一个效果。

**只要一个基于SpringBoot项目的类路径下存在SqlSessionFactory.class, SqlSessionFactoryBean.class，并且容器中已经注册了dataSourceBean，就可以触发自动化配置**，意思说我们**只要在maven的项目中加入了mybatis所需要的若干依赖，就可以触发自动配置**，但引入mybatis原生依赖的话，每集成一个功能都要去修改其自动化配置类，那就得不到开箱即用的效果了。所以Spring-boot为我们提供了统一的starter可以直接配置好相关的类，触发自动配置所需的依赖(mybatis)如下：

```
<dependency>
            <groupId>org.mybatis.spring.boot</groupId>
            <artifactId>mybatis-spring-boot-starter</artifactId>
</dependency>
```

因为maven依赖的传递性，我们只要依赖starter就可以依赖到所有需要自动配置的类，实现开箱即用的功能。也体现出Springboot简化了Spring框架带来的大量XML配置以及复杂的依赖管理，让开发人员可以更加关注业务逻辑的开发。



其他的*AutoConfiguration类都是类似的。



#### 8. 怎么关闭自动配置？

只有spring.boot.enableautoconfiguration为true（默认为true）的时候，才启用自动配置，所以我们可以配置spring.boot.enableautoconfiguration=false禁用自动配置。

 @EnableAutoConfiguration还可以进行排除，排除方式有2中，一是根据class来排除（exclude），二是根据class name（excludeName）来排除