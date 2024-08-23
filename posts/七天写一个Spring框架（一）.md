七天写一个Spring框架（一）
2024-08-22
七天手写一个Spring轻量级框架之第一天
06.jpg
造轮子系列
huizhang43

今天实现的类图

在spring-beans中的实现

![img](http://pcc.huitogo.club/ad113a06e1facacd9ff212e09a42c1d6)



在spring-context中的实现

![img](http://pcc.huitogo.club/8f79d598c22af10d2b5ae78e59e551fc)



第二天我们的目标是

#### **1、分割DefaultBeanFactory**

将解析xml和装载Bean的过程和暴露出去的获取bean过程分割开来，毕竟我们希望暴露给别人使用的部分越简单越好。

这里我们定义一个接口去操作beanDefinition，让原有的BeanFacory只做getBean()操作

```
1.  public interface BeanDefinitionRegistry {  

2.      BeanDefinition getBeanDefinition(String id);  

3.      void registryBeanDefinition(String id, BeanDefinition bd);  

4.  } 
```



我们需要一个类去解析xml配置文件，然后调用上面BeanDefinitionRegistry接口的registryBeaDefinition()方法，前提是这个类有BeanDefinitionRegistry的实例，我们可以在构造方法里面给它赋值。

我们新增**XmlBeanDefinitionReader**类

```
1.  public class XmlBeanDefinitionReader {  

2.      public static final String ID_ATTRIBUTE = "id";  

3.      public static final String CLASS_ATTRIBUTE = "class";  

4.      public static final String SCOPE_ATTRIBUTE = "scope";  

5.      BeanDefinitionRegistry registry;  

6.      public XmlBeanDefinitionReader(BeanDefinitionRegistry registry) {  

7.          this.registry = registry;  

8.      }  

9.      public void loadBeanDefinition(Resource resource) { // 修改一  

10.         InputStream is = null;  

11.         try {  

12.             is = resource.getInputStream();  

13.             SAXReader reader = new SAXReader();  

14.             Document doc = reader.read(is);  

15.             Element root = doc.getRootElement();  

16.             Iterator<Element> itr = root.elements().iterator();  

17.             while (itr.hasNext()) {  

18.                 Element ele = itr.next();  

19.                 String id = ele.attributeValue(ID_ATTRIBUTE);  

20.                 String beanClassName = ele.attributeValue(CLASS_ATTRIBUTE);  

21.                 BeanDefinition bd = new GenericBeanDefinition(id, beanClassName);  

22. //              if(ele.attribute(SCOPE_ATTRIBUTE) != null) {  // 判断bean的scope  // 修改二  

23. //                  bd.setScope(ele.attributeValue(SCOPE_ATTRIBUTE));  

24. //              }  

25. // 这里用BeanDefinitionRegistry 替代了container  

26.                 this.registry.registryBeanDefinition(id, bd);   /

27.             }  

28.         } catch (DocumentException | IOException e) {  

29.             throw new BeanStoreException("configFile is valid xml file!");  

30.         } finally {  

31.             if (is != null) {  

32.                 try {  

33.                     is.close();  

34.                 } catch (IOException e) {  

35.                     e.printStackTrace();  

36.                 }  

37.             }  

38.         }  

39.     }  

40. }  
```



整体步骤跟之前DefaultBeanFactory的地方差不多，但是多了两个改动（修改一和修改二），后面再说，也是这次的目标

到此解析xml的流程就做完了，然后就是让DefaultBeanFactory去实现BeanDefinitionRefgistry，利用BeanDefinitionRefgistry.getBeanDefinition()方法获取BeanDefinition。



#### **2、获取配置文件的方式**

我们第一天加载xml配置文件的方式是从类运行环境中去获取，即

```
1.  ClassLoader cl = ClassUtils.getDefaultClassLoader();  

2.  is = cl.getResourceAsStream(configFile); 
```

但实际过程中，我们可能需要各个途径去加载xml，比如文件系统、网络url等。

所以我们抽象出一个Resource接口用于描述xml加载方法，最终我们是希望从这个Resource中获取一个InputStream用来解析



定义**Resource**接口

```
1.  public interface Resource {  

2.      public InputStream getInputStream() throws IOException;  

3.      public String getDescription();  

4.  }  
```



从类环境加载xml，注意这里的ClassPathResource配置文件是可以配置ClassLoader的

```
1.  public class ClassPathResource implements Resource {  

2.      private final String configFile;  

3.      private ClassLoader classLoader;  

4.      public ClassPathResource(String configFile) {  

5.          this(configFile, (ClassLoader)null);  

6.      }  


7.      public ClassPathResource(String configFile, ClassLoader classLoader) {  

8.          Assert.notNull(configFile, "configFile must not be null!");  

9.          this.configFile = configFile;  

10.         this.classLoader = classLoader != null ? classLoader : ClassUtils.getDefaultClassLoader();  

11.     }  


12.     @Override  

13.     public InputStream getInputStream() throws IOException {  

14.         return classLoader.getResourceAsStream(configFile);  

15.     }  


16.     @Override  

17.     public String getDescription() {  

18.         return "configFile []";  

19.     }  

20. }  
```



从文件系统中加载xml

```
1.  public class FileSystemResource implements Resource {  

2.      private final String path;  

3.      private final File file;  

4.      public FileSystemResource(String path) {  

5.          Assert.notNull(path, "Path must not be null");  

6.          this.path = path;  

7.          this.file = new File(path);  

8.      }  


9.      @Override  

10.     public InputStream getInputStream() throws IOException {  

11.         return new FileInputStream(file);  

12.     }  

13.     @Override  

14.     public String getDescription() {  

15.         return "file [" + this.file.getAbsolutePath() + "] ";  

16.     }  

17. } 
```



有了这些之后我们就可以回到修改一，就是这么来的

```
1.  XmlBeanDefinitionReader.loadBeanDefinition(Resource resource){  

2.      //...                

3.          is = resource.getInputStream();  

4.      //...  

5.  }  
```



#### **3、Bean的单例模式**

我们都知道spring默认生成的bean都是单例模式的，那我们怎么实现这个呢？

首先我们肯定要在解析xml的时候去看下bean的scope属性是什么，然后设置到对应的BeanDefinition上，默认是单例的，所以没有设置scope属性的时候就是单例的

其次就是在getBean的时候，判断获取到的BeanDefinition是不是单例的，是的话就返回同一个Bean，这里我们可以考虑用一个ConcurrentHashMap去实现

从上面思路出发，单例模式我们认为是一种行为，新建一个接口DefaultSingletonBeanRegistry负责去接收单例Bean



DefaultSingletonBeanRegistry接口如下：

```
1.  // 将一个bean放入单例map中和从单例Map中获取bean，是控制scope的核心方法 

2.  public class DefaultSingletonBeanRegistry implements SingletonBeanRegistry {  

3.      private final Map<String, Object> singletonObjects = new ConcurrentHashMap<>();  

4.      @Override  

5.      public void registrySingleton(String beanName, Object singletonObject) {  

6.          Assert.notNull(beanName, "beanName must not be null");  

7.          Object oldObject = this.singletonObjects.get(beanName);  

8.          if(oldObject != null) {  

9.              throw new IllegalStateException("there is already exists " + beanName + "object");  

10.         }  

11.         this.singletonObjects.put(beanName, singletonObject);  

12.     }  

13.     @Override  

14.     public Object **getSingleton**(String beanName) {  

15.         return singletonObjects.get(beanName);  

16.     }  

17. } 
```



有了这个接口，首先修改一下BeanDefinition接口，增加scope相关属性和方法

```
1.  public interface BeanDefinition {  

2.      static final String SCOPE_DEFAULT = ""; // scope默认值  

3.      static final String SCOPE_SINGLETON = "singleton";   

4.      static final String SCOPE_PROTOTYPE = "prototype";   

5.      String getClassName();  

6.      String getId();  

7.      boolean isSingleton();   

8.      boolean isPrototype();  

9.      String getScope();  

10.     void setScope(String scope);  

11. }  
```



对应的默认实现类GenericBeanDefinition修改如下，注意setScope方法，因为默认scope就是singleton的

```
1.  @Data  

2.  public class GenericBeanDefinition implements BeanDefinition {  

3.      private String id;  

4.      private String className;  

5.      private boolean singleton = true;  

6.      private boolean prototype = false;  

7.      private String scope = SCOPE_DEFAULT;  

8.      public GenericBeanDefinition(String id, String className) {  

9.          super();  

10.         this.id = id;  

11.         this.className = className;  

12.     }  

13.     @Override  

14.     public boolean isSingleton() {  

15.         return this.singleton;  

16.     }  

17.     @Override  

18.     public boolean isPrototype() {  

19.         return this.prototype;  

20.     }  

21.     @Override  

22.     public String getScope() {  

23.         return this.scope;  

24.     }  

25.     @Override  

26.     public void setScope(String scope) {  

27.         this.scope = scope;  

28.         this.singleton = SCOPE_SINGLETON.equals(scope) || SCOPE_DEFAULT.equals(scope);  

29.         this.prototype = SCOPE_PROTOTYPE.equals(scope);  

30.     }  

31. }  
```



修改完了BeanDefinition后，**在解析xml的时候设置scope属性**

这也就是XmlBeanDefinitionReader.loadBeanDefinition修改二的内容

```
1.  if(ele.attribute(SCOPE_ATTRIBUTE) != null) {  // 判断bean的scope   

2.      bd.setScope(ele.attributeValue(SCOPE_ATTRIBUTE));  

3.  }  
```

设置好scope属性，在getBean的时候判断单例，是单例就从DefaultSingletonBeanRegistry的concurrentHashMap中取bean（同一个bean），不是就反射创建一个bean并加入concurrentHashMap中



DefaultBeanFactory的相关代码修改如下：

```
1.  @Override  

2.  public Object getBean(String beanId) {  

3.      //...

4.   // 判断单例和获取单例Bean

5.      if(bd.isSingleton()) {   

6.          Object bean = this.getSingleton(beanId);  

7.          if(bean == null) {  

8.              bean = createBean(bd);  

9.              this.registrySingleton(beanId, bean);  

10.         }  

11.         return bean;  

12.     }  

13.     return createBean(bd);  

14. }    

15. }  
```



#### **4、使用ApplicationContext封装**

在上面步骤都完成后，我们getBean需要的步骤是这样的

```
1.  DefaultBeanFactory beanFactory = new DefaultBeanFactory();  

2.  XmlBeanDefinitionReader reader = new XmlBeanDefinitionReader(beanFactory);  

3.  ClassPathResource resource = new ClassPathResource("applicationContext.xml");  

4.  reader.loadBeanDefinition(resource);  

5.  BeanDefinition bd = beanFactory.getBeanDefinition("student");  

6.  Student student = (Student) beanFactory.getBean("student");  
```



可以看的出来非常繁杂，虽然我们确实实现了各功能分离，那么我们使用过Spring都知道Spring是怎么操作的，类似一下这种

```
1.  ApplicationContext context = new ClassPathXmlApplicationContext("applicationContext.xml");  

2.  Student student = (Student)context.getBean("student")
```



这样就很清晰了，那我们怎么实现这种效果呢

首先定义一个ApplicationContext接口，里面有getBean方法

然后根据不同加载xml的方式实现不同的类，比如ClassPathXmlApplicationContext和FileSystemXmlApplicationContext，故名思意就是从类环境和文件系统中加载文件



**ClassPathXmlApplicationContext**代码如下：

```
1.  public abstract class ClassPathXmlApplicationContext implements ApplicationContext {  

2.      private DefaultBeanFactory factory = null;  

3.      public ClassPathXmlApplicationContext(String path) {  

4.          factory = new DefaultBeanFactory();  

5.          XmlBeanDefinitionReader reader = new XmlBeanDefinitionReader(factory);  

6.          Resource resource = new ClassPathResource(path);  

7.          reader.loadBeanDefinition(resource);  

8.      }  

9.      public Object getBean(String beanId) {  

10.         return factory.getBean(beanId);  

11.     }  

12. }  
```



当我们写**FileSystemXmlApplicationContext**代码的时候发现跟ClassPathXmlApplicationContext非常雷同，区别就是获取Resource的方式不一样

这时候 我们 思考使用**模板方法**来合并FileSystemXmlApplicationContext和ClassPathXmlApplicationContext以及更多类似的内容。

定义一个抽象类**AbstractApplicationContext**继承ApplicationContext，将公有代码放在这个抽象类中，因为不同的Context之间就是Resource不一样，于是在AbstractApplicationContext抽象类中定义一个getResource方法让下面的类去实现

最后的类图如下：

![img](http://pcc.huitogo.club/8f79d598c22af10d2b5ae78e59e551fc)



AbstractApplicationContext代码如下

```
1.  public abstract class AbstractApplicationContext implements ApplicationContext {  

2.      private DefaultBeanFactory factory = null;  

3.      public AbstractApplicationContext(String path) {  

4.          factory = new DefaultBeanFactory();  

5.          XmlBeanDefinitionReader reader = new XmlBeanDefinitionReader(factory);  

6.          Resource resource = this.getResourceByPath(path);  

7.          reader.loadBeanDefinition(resource);  

8.      }  

9.      public Object getBean(String beanId) {  

10.         return factory.getBean(beanId);  

11.     }  

12.     protected abstract Resource getResourceByPath(String path);  

13. }  
```



修改后ClassPathXmlApplicationContext代码

```
1.  public class ClassPathXmlApplicationContext extends AbstractApplicationContext {  

2.  //...  

3.      @Override  

4.      protected Resource getResourceByPath(String path) {  

5.          return new ClassPathResource(path, this.getClassLoader());  

6.      }  

7.  } 
```



FileSystemXmlApplicationContext代码

```
1.  public class FileSystemXmlApplicationContext extends AbstractApplicationContext{  

2.  //...  

3.      @Override  

4.      protected Resource getResourceByPath(String path) {  

5.          return new FileSystemResource(path);  

6.      }  

7.  }  
```



#### **5、自定义classLoader**

在ClassPathResource中我们说过它的构造方法允许自定义ClassLoader的，通过ClassLoader来解析xml，但是在上面构建ApplicationContext的过程中，ClassLoader一直都是默认（getDefaultClassLoader）的，

怎么传入自定义的classLoader呢？



秉着分离的原则，还是定义接口实现新的行为

定义**ConfigurableBeanFactory**接口来实现classLoader的 (getter/setter)

然后ApplicationContext来继承这个ConfigurableBeanFactory接口，在使用过程中可以直接setClassLoader到ClassPathResouce的classLoader中



ConfigurableBeanFactory接口

```
1.  public interface ConfigurableBeanFactory extends BeanFactory {  

2.      void setClassLoader(ClassLoader cl);  

3.      ClassLoader getClassLoader();  

4.  }  
```



修改AbstractApplicationContext的部分如下：

```
1.  public abstract class AbstractApplicationContext implements ApplicationContext {  

2.      private ClassLoader cl;  

3.      public AbstractApplicationContext(String path) {  

4.          //...  

5.          factory.setClassLoader(cl);  

6.      }  

7.      @Override  

8.      public void setClassLoader(ClassLoader cl) {  

9.          this.cl = cl;  

10.     }  

11.     @Override  

12.     public ClassLoader getClassLoader() {  

13.         return this.cl != null ? cl : ClassUtils.getDefaultClassLoader();  

14.     }  

15. }  
```