七天写一个Spring框架（准备）
2024-08-22
七天手写一个Spring轻量级框架之准备工作
06.jpg
造轮子系列
huizhang43

今天开始跟着刘欣老师学spring，来一次重复造轮子

开始之前首先普及一下TDD的开发理念，也就是测试驱动开发，使用充分的测试方法和测试用例来保证每一个方法的正确性，更重要的是保证后面开发的代码不会影响前面的开发部分，步骤如下：

- 思考用例
- 启动失败
- 编写just enough代码 让测试通过
- 重构代码 让测试通过]

今天学习的主要目标，从spring的xml配置文件中获取我们定义的bean实例

类图如下：

![img](http://pcc.huitogo.club/d985d56d3e983d44ba4681ad64b9eb8c)



首先摆出测试用例

```
1.  @Test  

2.  public void testGetBean()  

3.          throws ClassNotFoundException, InstantiationException, IllegalAccessException, DocumentException {  

4.      BeanFactory beanFactory = new DefaultBeanFactory("applicationContext.xml");  

5.      BeanDefinition bd = beanFactory.getBeanDefinition("car");  

6.      assertEquals("my_spring.beanfactory.bean.Car", bd.getClassName());  

7.      Car car = (Car) beanFactory.getBean("car");  

8.      assertNotNull(car);  

9.  }  


10. @Test  

11. public void testValidBean() {  

12.     BeanFactory beanFactory = new DefaultBeanFactory("applicationContext.xml");  

13.     try {  

14.         beanFactory.getBean("invalidBean");  

15.     } catch (BeanCreateException e) {  

16.         return;  

17.     }  

18.     Assert.fail("unexpected result");  

19. }  


20. @Test  

21. public void testValidXml() {  

22.     BeanFactory beanFactory;  

23.     try {  

24.         beanFactory = new DefaultBeanFactory("appxxx.xml");  

25.     } catch (BeanStoreException e) {  

26.         return;  

27.     }  

28.     beanFactory.getBean("car");  

29.     Assert.fail("unexpected result");  

30. } 
```



我们需要定义一个BeanFactory接口 封装了对Bean操作的方法，主要是getBean(String beanName)

```
1.  public interface BeanFactory {  

2.      Object getBean(String string);  

3.      BeanDefinition getBeanDefinition(String string);  

4.  }  
```



再定义一个BeanDefinition接口封装了Bean的属性

```
1.  public interface BeanDefinition {  

2.      String getClassName();  

3.      String getId();  

4.  }  
```



定义一个GenericBeanDefinition类默认实现BeanDefinition

```
1.  @AllArgsConstructor  

2.  @Data  

3.  public class GenericBeanDefinition implements BeanDefinition {  

4.      private String id;  

5.      private String className;  

6.  }  
```



定义一个DefaultBeanFactory类默认实现BeanFactory接口

这里我们希望利用DefaultBeanFactory构造方法去解析spring的xml配置文件，将解析出来的bean放入map中，map的key是beanName，value就是beanDefinition

```
1.  public DefaultBeanFactory(String configFile) {  

2.      loadBeanDefinition(configFile); // 装载xml配置文件  

3.  }  

4.  private void loadBeanDefinition(String configFile) {  

5.      InputStream is = null;  

6.      try {  

7.          ClassLoader cl = ClassUtils.getDefaultClassLoader();  

8.          is = cl.getResourceAsStream(configFile); // 从当前类加载环境中获取配置文件  

9.          SAXReader reader = new SAXReader(); // dom4j解析xml  

10.         Document doc = reader.read(is);  

11.         Element root = doc.getRootElement();  

12.         Iterator<Element> itr = root.elements().iterator();  

13.         while(itr.hasNext()) { // 遍历bean xml标签放入map中  

14.             Element ele = itr.next();  

15.             String id = ele.attributeValue(ID_ATTRIBUTE);  

16.             String beanClassName = ele.attributeValue(CLASS_ATTRIBUTE);  

17. // 生成BeanDefinition  

18.             BeanDefinition bd = new GenericBeanDefinition(id, beanClassName); 

19.             container.put(id, bd);  

20.         }  

21.     } catch (DocumentException e) {  

22.         throw new BeanStoreException(configFile + "is valid xml file!");  

23.     } finally {  

24.         if(is != null) {  

25.             try {  

26.                 is.close();  

27.             } catch (IOException e) {  

28.                 e.printStackTrace();  

29.             }  

30.         }  

31.     }  

32. }  
```



实现BeanFactory的getBean()和getBeanDefinition()方法，通过上面代码我们可以直接从map中根据key去取出对应的BeanDefinition即可，对于getBean()需要返回的Object，我们直接通过BeanDefinition的className反射获取。

```
1.  @Override  

2.  public BeanDefinition getBeanDefinition(String beanId) {  

3.      return container.get(beanId);  

4.  }  

5.  @Override  

6.  public Object getBean(String beanId) {  

7.      BeanDefinition bd = container.get(beanId);  

8.      if(bd == null){  

9.          throw new BeanCreateException("Bean is not definied!");  

10.     }  

11.     String className = bd.getClassName();  

12.     ClassLoader cl = ClassUtils.getDefaultClassLoader();  // 反射获取实例  

13.     try {  

14.         Class<?> clazz = cl.loadClass(className);  

15.         return clazz.newInstance();  

16.     } catch (Exception e) {  

17.         throw new BeanCreateException("create bean " + className + "failed!");  

18.     }   

19. }  
```

上面的代码中我们做出一个小优化，使用自定义Exception做异常处理，比如在loadBeanDefinition时抛出的BeanStoreException表示装载xml中出现的异常，在getBean时抛出的BeanCreateException表示获取Bean时（无效bean等）出现的异常，在Spring中还有很多这种自定义异常。