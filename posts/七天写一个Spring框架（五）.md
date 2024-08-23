七天写一个Spring框架（五）
2024-08-22
七天手写一个Spring轻量级框架之第五天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/cc2ab9a9034f11351c1557eeecd63236)



**今天的目标是**

帮助实例BeanA中被@Autowired修饰的字段或方法进行实例化，并且将这个实例化的Bean赋给实例BeanA，也就是实现通过@Autowired的方法为实例A赋属性值。

实现的总体思想先将@Autowired修饰的字段或方法转换成对应的Bean，然后如果是字段的话就直接将这个Bean赋值给这个字段，如果是set方法的话，就反射调用这个set方法完成赋值，最后需要考虑在一个合适的时机调用这些实例化和赋值操作。



#### **1、转换Bean**

第一步将@Autowired修饰的字段或方法转换成对应的Bean

我们需要一个类来表示被@Autowired修饰的方法或者字段

这里新建一个类DependencyDescriptor

```
1.  public class DependencyDescriptor {  

2.      //被修饰的字段  

3.      private final  Member member;  

4.      //是否必须有值存在  

5.      private final boolean required;  

6.      public DependencyDescriptor(Member member, boolean required) {  

7.          this.member = member;  

8.          this.required = required;  

9.      }  

10.     public Class<?> getDependencyType(){  

11.         if(this.member instanceof Field) {  

12.             Field field = (Field) member;  

13.             return field.getType();  

14.         }  

15.         // 如果是放在setter方法上，取第一个参数的类型  

16.         if(this.member instanceof Method) {   

17.             Method method = (Method)member;  

18.             return method.getParameterTypes()[0];  

19.         }  

20.         throw new RuntimeException("only support field and method dependency");  

21.     }  

22.     public boolean isRequired() {  

23.         return required;  

24.     }  

25. }  
```

这里getDependencyType()可以根据修饰的类型获取对应的Class。

现在我们赋予BeanFactory新的能力，可以根据DependencyDescriptor（其实就是想要里面解析出来的Class）映射Bean，这里的Bean自然就是BeanFactory的Bean容器里面的



定义新的接口AutowiredCapableBeanFactory和它的实现

```
1.  public interface AutowiredCapableBeanFactory{  

2.      Object resolveDependency(DependencyDescriptor descriptor);  

3.  }  


4.  public class DefaultBeanFactory extends DefaultSingletonBeanRegistry  

5.          implements BeanDefinitionRegistry, ConfigurableBeanFactory, AutowiredCapableBeanFactory {  

6.     //...  

7.     // 尝试解析descriptor中Class成BeanDefinition  

8.      @Override  

9.      public Object resolveDependency(DependencyDescriptor descriptor) {  

10.         Class<?> typeToMatch = descriptor.getDependencyType();  

11.         for (BeanDefinition bd : this.container.values()) {  

12.             resolveBeanClass(bd);  

13.             Class<?> beanClass = bd.getBeanClass();  

14.             if (typeToMatch.isAssignableFrom(beanClass)) {  

15.                 return this.getBean(bd.getId());  

16.             }  

17.         }  

18.         return null;  

19.     }  

20.      //...  

21. }  
```



好了，到此将字段、方法映射成对应的Bean就完成了，怎么用呢？

```
1.  @Test  

2.  public void testResolveDependency() throws NoSuchFieldException, SecurityException {  

3.      DefaultBeanFactory beanFactory = new DefaultBeanFactory();  

4.      XmlBeanDefinitionReader reader = new XmlBeanDefinitionReader(beanFactory);  

5.      reader.loadBeanDefinition(new ClassPathResource("applicationContext3.xml"));  

6.      Field f =  PersonService.class.getDeclaredField("eatDao");  

7.      DependencyDescriptor descriptor = new DependencyDescriptor(f, true);  

8.      Object o = beanFactory.resolveDependency(descriptor);  

9.      Assert.assertTrue(o instanceof EatDao);  

10. }  
```



#### **2、将转换的Bean赋给它所在的Bean A**

在此之前，我们需要对上面转换过程进行一次封装，Spring的实现过程就是一步步的封装隐藏细节，最后用一个类和方法来实现所需要的功能

所以，针对Field和Method以及其他情况，我们抽象出一个接口InjectionElement

```
1.  public abstract class InjectionElement {  

2.      protected Member member;  

3.      protected AutowiredCapableBeanFactory factory;  

4.      public InjectionElement(Member member, AutowiredCapableBeanFactory factory) {  

5.          super();  

6.          this.member = member;  

7.          this.factory = factory;  

8.      }  

9.      public abstract void inject(Object target);  

10. } 
```

这里最重要的就是inject的实现，它的作用就是将BeanFacotry.resolveDependency出来的Bean赋给target



这里来看一下Field的inject实现

```
1.  public class AutowiredFieldElement extends InjectionElement {  

2.      //...  

3.      @Override  

4.      public void inject(Object target) {   

5.          Field field = getField();  

6.          try {  

7.              DependencyDescriptor descriptor = new DependencyDescriptor(field, required);  

8.              Object fieldObj = factory.resolveDependency(descriptor);  

9.              if (fieldObj != null) {  

10.                 // 使field可用，在field为final、private修饰的情况下，accessible为false的  

11.                 ReflectionUtils.makeAccessible(field);  

12.                 field.set(target, fieldObj);  

13.             }else if (required) {  

14.                 throw new BeanAutowiredException("could not find a bean named["  

15.                         + descriptor.getDependencyType().getName() + "] used to autowired for" + target);  

16.             }  

17.         } catch (Throwable e) {  

18.             throw new BeanCreateException("could not autowird field :" + field, e);  

19.         }  

20.     }  

21.     //...  

22. }  
```

这里直接是通过 field.set(target, fieldObj); 赋值的



对应Method的inject实现

```
1.  public class AutowiredMethodElementextends InjectionElement {  

2.      //...  

3.      @Override  

4.      public void inject(Object target) {   

5.          Method method = getMethod();  

6.          try {  

7.              DependencyDescriptor descriptor = new DependencyDescriptor(method, required);  

8.              Object fieldObj = factory.resolveDependency(descriptor);  

9.              if (fieldObj != null) {  

10.                 // 使field可用，在field为final、private修饰的情况下，accessible为false的  

11.                 ReflectionUtils.makeAccessible(method);  

12.                 method.invoke(target, methodReturnObj);  

13.             }else if (required) {  

14.                 throw new BeanAutowiredException("could not find a bean named["  

15.                         + descriptor.getDependencyType().getName() + "] used to autowired for" + target);  

16.             }  

17.         } catch (Throwable e) {  

18.             throw new BeanCreateException("could not autowird method:" + method, e);  

19.         }  

20.     }  

21.     //...  

22. }  
```

可以看到Method是通过 method.invoke(target, methodReturnObj); 赋值的



听过你们好奇这个ReflectionUtils.makeAccessible()方法，来来来，贴下短小的源码

```
1.  public static void makeAccessible(Method method) {  

2.      if ((!Modifier.isPublic(method.getModifiers()) ||  

3.              !Modifier.isPublic(method.getDeclaringClass().getModifiers())) && !method.isAccessible()) {  

4.          method.setAccessible(true);  

5.      }  

6.  }  
```

除了Field和Method的情况，其实应该还有Constructor的情形，这里就没有实现了



在进行下一步之前，我们觉得对应每一个Method和Field难道都一个个去inject到target?

还是来封装一下吧，把这些InjectionElement放到一个List中去，然后统一inject，完美！

新建一个类InjectionMetadata来做这件事，它就负责将elements全部注入到targetClass中

```
1.  @Getter  

2.  public class InjectionMetadata {  

3.      private final Class<?> targetClass;  

4.      private final List<InjectionElement> elements;  

5.      public InjectionMetadata(Class<?> targetClass, List<InjectionElement> elements) {  

6.          this.targetClass = targetClass;  

7.          this.elements = elements;  

8.      }  

9.      public void inject(Object target) {  

10.         if(elements == null || elements.isEmpty()) {  

11.             return;  

12.         }  

13.         for(InjectionElement injectionElement : elements) {  

14.             injectionElement.inject(target);  

15.         }  

16.     }  

17. } 
```



这时候使用起来就是这样

```
1.  @Test  

2.  public void testInject() throws NoSuchFieldException, SecurityException {  

3.      DefaultBeanFactory beanFactory = new DefaultBeanFactory();  

4.      XmlBeanDefinitionReader reader = new XmlBeanDefinitionReader(beanFactory);  

5.      reader.loadBeanDefinition(new ClassPathResource("applicationContext3.xml"));  

6.      Class<?> clazz = PersonService.class;  

7.      LinkedList<InjectionElement> elements = new LinkedList<>();  

8.      {  

9.          Field f = clazz.getDeclaredField("eatDao");  

10.         InjectionElement injectionEle = new AutowiredFieldElement(f, true, beanFactory);  

11.         elements.add(injectionEle);  

12.     }  

13.     {  

14.         Field f = clazz.getDeclaredField("drinkDao");  

15.         InjectionElement injectionEle = new AutowiredFieldElement(f, true, beanFactory);  

16.         elements.add(injectionEle);  

17.     }  

18.     // 这里是真正的注入过程，将elemenets中的变量通过setter的方式放到clazz中  

19.     // metadata.inject()实质调用的是InjectionElement.inject()  

20.     InjectionMetadata metadata = new InjectionMetadata(clazz, elements);  

21.     PersonService personServie = new PersonService();  

22.     metadata.inject(personServie);  

23.     Assert.assertTrue(personServie.getEatDao() instanceof EatDao);  

24.     Assert.assertTrue(personServie.getDrinkDao() instanceof DrinkDao);  

25. }  
```



#### **3、将targetClass中所有被@Autowired修饰的地方转换成InjectionMeta**

第二步中，我们可以将一个Filed或Method转换成InjectionElement，并且可以inject到targetClass中，现在我们怎么获取或者筛选这些Field或者Method呢？

我们新建一个类AutowiredAnnotationProcessor来做这件事，它的任务就是在targetClass筛选出这些Field和Method并且转换成InjectionElement，最后组装一个InjectionMetadata返回出来



AutowiredAnnotationProcessor代码如下：

```
1.  public class AutowiredAnnotationProcessor{  

2.      private AutowiredCapableBeanFactory beanFactory;  

3.      private String requiredParameterName = "required";  

4.      private boolean requiredParameterValue = true;  

5.  //这里使用一个集合装载可以被解析的注释类

6.  private final Set<Class<? extends Annotation>> autowiredAnnotationTypes  = new LinkedHashSet<>();

7.     public AutowiredAnnotationProcessor() {

8.  this.autowiredAnnotationTypes.add(Autowired.class);

9.  }


10.     public InjectionMetadata buildAutowiringMetadata(Class<?> clazz) {  

11.         LinkedList<InjectionElement> elements = new LinkedList<>();  

12.         Class<?> targetClass = clazz;  

13.         do {  

14.             LinkedList<InjectionElement> currentElements = new LinkedList<>();  

15.             for (Field field : targetClass.getDeclaredFields()) {  

16.                 //查找@Autowired注释  

17.                 Annotation ann = findAutowiredAnnotation(field);  

18.                 if (ann != null) {  

19.                     // 确认被修饰的字段是否是static的  

20.                     if (Modifier.isStatic(field.getModifiers())) {  

21.                         continue;  

22.                     }  

23.                     boolean required = determinedRequiredStatus(ann);  

24.                     // 新增一条InjectionElement  

25.                     currentElements.add(new AutowiredFieldElement(field, required, beanFactory));  

26.                 }  

27.             }  

28.             for (Method method : targetClass.getDeclaredMethods()) {  

29.                 //查找@Autowired注释  

30.                 Annotation ann = findAutowiredAnnotation(method);  

31.                 if (ann != null) {  

32.                     // 确认被修饰的字段是否是static的  

33.                     if (Modifier.isStatic(method.getModifiers())) {  

34.                         continue;  

35.                     }  

36.                     boolean required = determinedRequiredStatus(ann);  

37.                     // 新增一条InjectionElement  

38.                     currentElements.add(new AutowiredMethodElement(method, required, beanFactory));  

39.                 }  

40.             }  

41.             elements.addAll(0, currentElements);  

42.             targetClass = targetClass.getSuperclass();  

43.         } while (targetClass != null && targetClass != Object.class);  

44.         return new InjectionMetadata(clazz, elements);  

45.     }  

46.     /** 

47.      * 在ao上查找autowiredAnnotationTypes中的注释 

48.      * 这里查找方式说明，如果在变量或者方法上面加上了@Autowired和@Resource注释的话，只会生效第一个 

49.      * @param ao 

50.      * @return 

51.      */  

52.     private Annotation findAutowiredAnnotation(AccessibleObject ao) {  

53.         for (Class<? extends Annotation> type : this.autowiredAnnotationTypes) {  

54.             Annotation ann = AnnotationUtils.getAnnotation(ao, type);  

55.             if (ann != null) {  

56.                 return ann;  

57.             }  

58.         }  

59.         return null;  

60.     }  


61.     /** 

62.      * 获取注释（这里指@Autowired）的required属性 

63.      * @param ann 

64.      * @return 

65.      */  

66.     private boolean determinedRequiredStatus(Annotation ann) {  

67.         try {  

68.             Method method = ReflectionUtils.findMethod(ann.annotationType(), this.requiredParameterName);  

69.             if (method == null) {  

70.                 return true;  

71.             }  

72.             return (this.requiredParameterValue == (Boolean) ReflectionUtils.invokeMethod(method, ann));  

73.         } catch (Exception e) {  

74.             return true;  

75.         }  

76.     }  
```

过程也不是很复杂，核心方法就是buildAutowiringMetadata()，这里需要注意的是筛选targetClass是一个do-while的过程，也就是我不仅要得到当前类的，还有它的父类的父类的父类，直到Object类。



#### **4、在合适的地方去调用AutowiredAnnotationProcessor.buildAutowiringMetadata()**

这里我们需要简单认识一下SpringBean的生命周期

初始化 --> 实例化 --> 执行中 --> 销毁，可以参考下图

![img](http://pcc.huitogo.club/2c269631f633da39d566bfa20a49ed97)



所以在Spring中是定义了这样的过程，抽象到一个更高的层次了。

新建BeanPostProcessor接口定义bean初始化前和初始化后的行为

```
1.  public interface BeanPostProcessor {  

2.      //初始化前  

3.      Object beforeInitialization(Object bean, String beanName) throws BeanExceptionn;  

4.      //初始化后  

5.      Object afterInitialization(Object bean, String beanName) throws BeanExceptionn;  

6.  }  
```



新建InstantiationAwareBeanPostProcessor接口定义bean实例化的过程

```
1.  public interface InstantiationAwareBeanPostProcessor extends BeanPostProcessor {  

2.      //实例化前  

3.      Object beforeInstantiation(Class<?> beanClass, String beanName) throws BeanExceptionn;  

4.      //实例化后  

5.      boolean afterInstantiation(Object bean, String beanName);  

6.      //注入属性

7.      void postProcessorPropertyValues(Object  bean, String beanName);  

8.  }  
```



我们希望AutowiredAnnotationProcessor是在实例化过程中赋值属性的

```
1.  public class AutowiredAnnotationProcessor implements InstantiationAwareBeanPostProcessor{  

2.  //...

3.      @Override  

4.      public void postProcessorPropertyValues(Object bean, String beanName) {  

5.          InjectionMetadata metadata = buildAutowiringMetadata(bean.getClass());  

6.          try {  

7.              metadata.inject(bean);  

8.          } catch (Throwable e) {  

9.              throw new BeanCreateException("Inject dependency failure!");  

10.         }  

11.     }      

12. }  
```



现在可以来实现第四步了，我们当然希望是在getBean的时候为这个Bean注入属性了，所以DefaultBeanFactory.populateBean()中进行实现

```
1.  public class DefaultBeanFactory extends DefaultSingletonBeanRegistry  

2.          implements BeanDefinitionRegistry, ConfigurableBeanFactory, AutowiredCapableBeanFactory {  

3.      //...  

4.      protected List<BeanPostProcessor> postProcessorsList = new ArrayList<>();  

5.      @Override  

6.      public void addBeanPostProcessor(BeanPostProcessor postProcessor) {  

7.          this.postProcessorsList.add(postProcessor);  

8.      }  

9.      @Override  

10.     public List<BeanPostProcessor> getBeanPostProcessor() {  

11.         return this.postProcessorsList;  

12.     }  


13.     /** 

14.      * 给bean设置赋值（注入）属性 

15.      * @param bd 

16.      * @param bean 

17.      */  

18.     private void populateBean(BeanDefinition bd, Object bean) {  

19.         // 为bean Autowired属性  

20.         // 这里说明在bean中@Autowired的属性会在getBean的时候进行注入  

21.         for (BeanPostProcessor processor : this.getBeanPostProcessor()) {  

22.             // 是否有实例化的BeanPostProcessor  

23.             if (processor instanceof InstantiationAwareBeanPostProcessor) {  

24.                 ((InstantiationAwareBeanPostProcessor) processor).postProcessorPropertyValues(bean, bd.getClassName());  

25.             }  

26.         }  

27.         //...  

28.     }  

29.     //  

30. }  
```

这里需要注意的是，DefaultBeanFactory里面维护的是一个BeanPostProcessor列表，这里不仅考虑的是在getBean之前为这个Bean注入属性，而是所有需要在Bean初始化前和初始化后以及实例化前和实例化后的操作，是一个更高的层次！Bean生命周期过程在这里体现！



#### **5、总结**

1）跳出当前这个点，往高处看，不要面向实现，对所有实现的操作都进行封装，到最后最好用一个接口和类就可以得到想要的结果，比如Spring中的ApplicationContext接口。

2）理解了Bean的生命周期。

3）对于抽象出来使用的接口是越简单越好。