七天写一个Spring框架（六）
2024-08-22
七天手写一个Spring轻量级框架之第六天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/b41e9c6cbed4ccfbad222c83104ba367)



**今天的目标是**

完成Spring Aop的上半节，比如现在给一个方法，和一堆拦截器，我希望这些拦截器可以有序执行，没错，就是Spring Aop中切面上拦截器链怎么执行的。



#### **1、识别哪些方法需要被拦截**

通常我们使用aop的时候都会定义一个切面，切面中有个重要的pointcut表达式，这个表达式定义着哪些方法需要被增强，第一步就是根据pointcut判断某个方法需不需要被增强

这里Spring实现没有自己去实现，而是直接使用了AspectJ里面的方法进行实现



这些新建一个类AspectJExpressionPointcut，代码如下：

```
1.  @Getter  

2.  @Setter  

3.  public class AspectJExpressionPointcut implements Pointcut, MethodMatcher {  

4.      private static final Set<PointcutPrimitive> SUPPORTED_PRIMITIVES = new HashSet<>();  

5.      static {  

6.          SUPPORTED_PRIMITIVES.add(PointcutPrimitive.EXECUTION);  

7.          SUPPORTED_PRIMITIVES.add(PointcutPrimitive.ARGS);  

8.          SUPPORTED_PRIMITIVES.add(PointcutPrimitive.REFERENCE);  

9.          SUPPORTED_PRIMITIVES.add(PointcutPrimitive.THIS);  

10.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.TARGET);  

11.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.WITHIN);  

12.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.AT_ANNOTATION);  

13.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.AT_WITHIN);  

14.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.AT_ARGS);  

15.         SUPPORTED_PRIMITIVES.add(PointcutPrimitive.AT_TARGET);  

16.     }  

17.     private String expression;  

18.     private PointcutExpression pointcutExpression;  

19.     private ClassLoader pointcutClassLoader;  

20.     public AspectJExpressionPointcut() {  

21.     }  

22.     @Override  

23.     public boolean match(Method method) {  

24.         //参数校验并解析expression为PointcutExpression  

25.         checkReadytoMatch();  

26.         //返回method是否匹配PointcurExpression  

27.         ShadowMatch shadowMatch = getShadowMatch(method);  

28.         if (shadowMatch.alwaysMatches()) {  

29.             return true;  

30.         }  

31.         return false;  

32.     }  


33.     private void checkReadytoMatch() {  

34.         if (getExpression() == null) {  

35.             throw new IllegalStateException("Must set property 'expression' before attempting to match");  

36.         }  

37.         if (this.pointcutExpression == null) {  

38.             this.pointcutClassLoader = ClassUtils.getDefaultClassLoader();  

39.             this.pointcutExpression = buildPointcutExpression(this.pointcutClassLoader);  

40.         }  

41.     }  

42.     /** 

43.      * 解析expression为PointcutExpression 

44.      * @param classLoader 

45.      * @return 

46.      */  

47.     private PointcutExpression buildPointcutExpression(ClassLoader classLoader) {  

48.         PointcutParser parser = PointcutParser .getPointcutParserSupportingSpecifiedPrimitivesAndUsingSpecifiedClassLoaderForResolution(  

50.                         SUPPORTED_PRIMITIVES, classLoader);  

51.         return parser.parsePointcutExpression(replaceBooleanOperators(getExpression()), null, new PointcutParameter[0]);  

52.     }  


53.     private String replaceBooleanOperators(String expression) {  

54.         String result = StringUtils.replace(expression, " and ", " && ");  

55.         result = StringUtils.replace(expression, " or ", " || ");  

56.         result = StringUtils.replace(expression, " not ", " ! ");  

57.         return result;  

58.     }  


59.     private ShadowMatch getShadowMatch(Method method) {  

60.         ShadowMatch shadowMatch = null;  

61.         shadowMatch = this.pointcutExpression.matchesMethodExecution(method);  

62.         return shadowMatch;  

63.     }  

64.     @Override  

65.     public MethodMatcher getMethodMatcher() {  

66.         return this;  

67.     }  

68. }  
```



这里主要就是将配置文件里面的pointcut表示式转换成AspectJ的PointcutExpression，然后做一下mathch操作，也就是下面这个操作

```
1.      private PointcutExpression buildPointcutExpression(ClassLoader classLoader) {  

2.          PointcutParser parser = PointcutParser  

3.                  .getPointcutParserSupportingSpecifiedPrimitivesAndUsingSpecifiedClassLoaderForResolution(  

4.                          SUPPORTED_PRIMITIVES, classLoader);  

5.          return parser.parsePointcutExpression(replaceBooleanOperators(getExpression()), null, new PointcutParameter[0]);  

6.      } 
```



#### **2、根据aop配置文件定位被增强的方法**

比如我们aop配置的文件如下

```
1.  <bean id="tx" **class**="my_spring.beanfactory_aop.test.tx.TransactionManager" />  

2.  <aop:config>  

3.      <aop:aspect ref="tx">  

4.          <aop:pointcut expression="execution(* my_spring.beanfactory_aop.test.service.*.placeOrder(..))" id="placeOrder"/>  

5.          <aop:before  method="start" pointcut-ref="placeOrder"></aop:before>  

6.          <aop:after-throwing method="rollback" pointcut-ref="placeOrder"/>  

7.          <aop:after-returning method="commit" pointcut-ref="placeOrder"/>  

8.      </aop:aspect>  

9.  </aop:config>  
```



我们肯定是想知道，这个<aop:before>里面的start方法是什么方法，到底存不存在，所以我们先实现怎么去找到这个start方法

实现的思路很简单，从Beafactory中去找这个ref=”tx”里面tx对应的bean，然后获取它的start方法就可以了

新建MethodLocatingFactory，相关代码如下：

```
1.  @Getter  

2.  @Setter  

3.  public class MethodLocatingFactory {  

4.      private String methodName;  

5.      private String targetBeanName;  

6.      private Method method;  

7.      public void setBeanFactory(DefaultBeanFactory beanFactory) throws NoSuchBeanDefinitionException {  

8.          if(!StringUtils.hasText(this.targetBeanName)) {  

9.              throw new IllegalArgumentException("Property 'targetBeanName' is required" );  

10.         }  

11.         if(!StringUtils.hasText(this.methodName)) {  

12.             throw new IllegalStateException("Property 'methodName' is required" );  

13.         }  

14.         Class<?> beanClass = beanFactory.getType(this.targetBeanName);  

15.         if(beanClass == null) {  

16.             throw new IllegalArgumentException("Can`t determine type of bean with name'" + this.targetBeanName + "'");  

17.         }  

18.         // 获取相关方法  

19.         this.method = BeanUtils.resolveSignature(this.methodName, beanClass);  

20.         if(this.method == null) {  

21.             throw new IllegalStateException("Unable to locate method [" + this.methodName + "] on bean [" + this.targetBeanName +"]");    

22.         }  

23.     }  


24.     public Method getObject() {  

25.         return this.method;  

26.     }  

27. }  
```



#### **3、拦截器链的有序调用**

现在我们可以考虑这里怎么实现拦截器链的有序调用

其实对于方法的增强，也就是在方法上加上一个拦截器，在aop中叫做**MethodInterceptor**，Spring在这基础上做了进一步的扩展，也就是**Advice**，针对方法前后等不同位置和不同功能的拦截器就又区分为**AspectJAfterAdvice**、**AspectJBeforeAdvice**等。

关系如下图：

![img](http://pcc.huitogo.club/cb188101cba7ee280cfd6ecba8e3e20e)



Advice和相关子类代码如下，其中Advice的子类没有一一列举

```
1.  public interface Advice extends MethodInterceptor {  

2.      public Pointcut getPointcut();  

3.  }     

4.  /** 

5.   * Advice接口的模板类 

6.   */  

7.  public abstract class AbstractAspectJAdvice implements Advice {  

8.      private Method adviceMethod;  

9.      private Pointcut pointcut;  

10.     private Object adviceObject;  

11.     public AbstractAspectJAdvice(Method adviceMethod, Pointcut pointcut, Object adviceObject) {  

12.         super();  

13.         this.adviceMethod = adviceMethod;  

14.         this.pointcut = pointcut;  

15.         this.adviceObject = adviceObject;  

16.     }  

17.     public void invokeAdviceMethod() throws Throwable {  

18.         adviceMethod.invoke(adviceObject);  

19.     }  

20.     @Override  

21.     public Pointcut getPointcut() {  

22.         return pointcut;  

23.     }  

24.     public Method getAdviceMethod() {  

25.         return this.adviceMethod;  

26.     }  

27. }  


28. public class AspectJAfterAdvice extends AbstractAspectJAdvice{  

29.     public AspectJAfterAdvice(Method adviceMethod, Pointcut pointcut, Object adviceObject) {  

30.         super(adviceMethod, pointcut, adviceObject);  

31.     }  

32.     //拦截的逻辑

33.     @Override  

34.     public Object invoke(MethodInvocation mi) throws Throwable {  

35.         Object o = mi.proceed();  

36.         this.invokeAdviceMethod();  

37.         return o;  

38.     }  

39. }  


40. public class AspectJAfterThrowingAdvice extends AbstractAspectJAdvice{  

41.     public AspectJAfterThrowingAdvice(Method adviceMethod, Pointcut pointcut, Object adviceObject) {  

42.         super(adviceMethod, pointcut, adviceObject);  

43.     }  

44.     //拦截的逻辑

45.     @Override  

46.     public Object invoke(MethodInvocation mi) throws Throwable {  

47.         try {  

48.             return mi.proceed();  

49.         } catch (Throwable e) {  

50.             this.invokeAdviceMethod();  

51.             throw e;  

52.         }  

53.     }  

54. }  
```



现在我们可以创建一堆Advice了，怎么在给定的方法上有序执行呢？

我们知道在MethodInterceptor的接口有个invoke方法，就是成功拦截到方法后需要做的操作，invoke方法的参数是一个MethodInvocation，那我们是否可以自己实现一个MethodInvocation去有序的调用那一堆Advice呢？

新建一个**ReflectiveMethodInvocation**去做这件事，相关代码如下：

```
1.  public class ReflectiveMethodInvocation implements MethodInvocation {  

2.      protected final Object targetObject;  

3.      protected final Method targetMethod;  

4.      protected Object[] arguments;  

5.      protected final List<MethodInterceptor>  interceptors;  

6.      private int currentInterceptrorIndex = -1;  

7.      public ReflectiveMethodInvocation(Object targetObject, Method targetMethod, Object[] arguments,  List<MethodInterceptor> interceptors) {  

8.          super();  

9.          this.targetObject = targetObject;  

10.         this.targetMethod = targetMethod;  

11.         this.arguments = arguments;  

12.         this.interceptors = interceptors;  

13.     }  

14.     @Override  

15.     public Object[] getArguments() {  

16.         return this.arguments;  

17.     }  

18.     @Override  

19.     public AccessibleObject getStaticPart() {  

20.         return this.targetMethod;  

21.     }  

22.     @Override  

23.     public Object getThis() {  

24.         return this.targetObject;  

25.     }  


26.     @Override  

27.     public Object proceed() throws Throwable {  

28.         //所有拦截器已经完成  

29.         if(this.currentInterceptrorIndex == this.interceptors.size() -1) {  

30.             return invokeJointpoint();  

31.         }  

32.         this.currentInterceptrorIndex ++;  

33.         MethodInterceptor interceptor = this.interceptors.get(currentInterceptrorIndex);  

34.         //这里会有一个递归的调用，每个Advice都会回调proceed()方法  

35.         return interceptor.invoke(this);  

36.     }  


37. //调用被拦截的方法

38.     private Object invokeJointpoint() throws IllegalAccessException, IllegalArgumentException, InvocationTargetException {  

39.         return this.targetMethod.invoke(this.targetObject, this.arguments);  

40.     }  

41.     @Override  

42.     public Method getMethod() {  

43.         return this.targetMethod;  

44.     }     

45. }  
```



这里可以看到有一个巧妙的设计，也就是每一个Advice里面的invoke都会调用ReflectiveMethodInvocation的procced方法，然后procced方法又会去调用Advice里面的invoke这样一个递归操作，直到每一个Advice都调用到了，才会真正去调用被拦截的方法。

这样做的话其实已经实现了我们想要的拦截器链的有序调用

所有被拦截的方法之前的增强内容已经调用到了，然后调用被拦截方法，最后是被拦截的方法之后的增强内容调用，所以说这种设计还是很巧妙的。



#### **4、aop增强的实现**

##### **（1）CGLIB的实现**

我们都知道Spring Aop的实现是预编译和动态代理，这里动态代理是既使用了jdk的动态代理，又包括了CGLIB。这里我们使用CGLIB实现方法的代理类，当然这个代理类已经对需要增强的方法进行了增强。



首先了解一下CGLIB的简单使用

```
1.  @Test  

2.  public void testCGLib() {  

3.      Enhancer enhancer = new Enhancer();  

4.      enhancer.setSuperclass(PersonService.class);  

5.      //设置拦截器  

6.      enhancer.setCallback(this);  

7.      PersonService personService = (PersonService) enhancer.create();  

8.      personService.placeOrder();  

9.  }  


10. @Test  

11. public void testFilter() {  

12.     Enhancer enhancer = new Enhancer();  

13.     enhancer.setSuperclass(PersonService.class);  

14.     enhancer.setInterceptDuringConstruction(false);  

15.     Callback[] callbacks = new Callback[] {this, NoOp.INSTANCE};  

16.     Class<?>[] types = new Class<?>[callbacks.length];  

17.     for(int i = 0; i < callbacks.length; i++) {  

18.         types[i] = callbacks[i].getClass();  

19.     }  

20.     //设置过滤器  

21.     enhancer.setCallbackFilter(new CGLibTest().new ProxyCallbackFilter());  

22.     enhancer.setCallbacks(callbacks);  

23.     enhancer.setCallbackTypes(types);  

24.     PersonService personService = (PersonService) enhancer.create();  

25.     personService.placeOrder();  

26.     personService.toString();  

27. }  

28. @Override  

29. public Object intercept(Object obj, Method targetMethod, Object[] args, MethodProxy proxy) throws Throwable {  

30.     TransactionManager tx = new TransactionManager();  

31.     tx.start();  

32.     Object result = proxy.invokeSuper(obj, args);  

33.     tx.commit();  

34.     return result;  

35. }  

36. class ProxyCallbackFilter implements CallbackFilter{  

37.     @Override  

38.     public int accept(Method method) {  

39.         // 如果拦截方法名以place开头，使用第一个拦截器  

40.         if(method.getName().startsWith("place")) {  

41.             return 0;  

42.         //否则使用第二个拦截器      

43.         }else {  

44.             return 1;  

45.         }  

46.     }  

47. }  
```

这里可以看到CGLIB使用了一个Enhancer中间类，可以利用这个Enhancer去指定需要被代理的类、拦截器MethodInterceptor和判断方法需要使用哪个拦截器的过滤器CallbackFilter，最后调用Enhancer.create()可以获取代理类。



现在我们知道怎么利用CGLIB去获取一个类增强后的代理类了，在Spring Aop中也是这么做的，生成代理类，代理类里面的每个方法进行拦截后都要和配置的Advice的PointcutExpression做Match判断，如果匹配执行符合条件的Advice的拦截器链，否则不做增强处理，直接调用被拦截的方法。

在此之前，Spring声明了一个Advised类来声明增强类的信息，相当于AdviceConfig

```
1.  public interface Advised {  

2.      Class<?> getTargetClass();  

3.      Object getTargetObject();  

4.      List<Advice> getAdvices();  

5.      void addAdvice(Advice advice);  

6.      List<Advice> getAdvices(Method method);  

7.  }  

8.  //Advised的默认实现类  

9.  public class AdvisedSupport implements Advised {  

10.     private Object targetObject = null;  

11.     private List<Advice> advices = new ArrayList<>();  

12.     public AdvisedSupport() {  

13.         super();  

14.     }  

15.     @Override  

16.     public Class<?> getTargetClass() {  

17.         return this.targetObject.getClass();  

18.     }  

19.     public void setTargetObject(Object targetObject) {  

20.         this.targetObject = targetObject;  

21.     }  

22.     @Override  

23.     public Object getTargetObject() {  

24.         return this.targetObject;  

25.     }  

26.     @Override  

27.     public List<Advice> getAdvices() {  

28.         return this.advices;  

29.     }  

30.     @Override  

31.     public void addAdvice(Advice advice) {  

32.         this.advices.add(advice);  

33.     }  

34.     @Override  

35.     public List<Advice> getAdvices(Method method) {  

36.         List<Advice> result = new ArrayList<>();  

37. // 对method做匹配操作

38.         for(Advice  advice : this.advices) {  

39.             Pointcut pc = advice.getPointcut();  

40.             if(pc.getMethodMatcher().match(method)) {  

41.                 result.add(advice);  

42.             }  

43.         }  

44.         return result;  

45.     }  

46. }  
```



这里Advised的最终目的就是获取method上符合条件的Advice

```
1.  if(pc.getMethodMatcher().match(method)) {  

2.      result.add(advice);  

3.  }  
```



有了被增强类和查找Advice的功能后，可以去实现获取这个被增强类的代理了

相关代码如下：

```
1.  public interface AopProxyFactory {  

2.      Object getProxy();  

3.      Object getProxy(ClassLoader classLoader);  

4.  }  

5.  public class CglibProxyFactory implements AopProxyFactory {  

6.      // 这些常量相当于是CallbackFilter中根据method返回的Interceptor的下标  

7.      private static final int AOP_PROXY = 0;  

8.      protected Logger log = LoggerFactory.getLogger(CglibProxyFactory.class);  

9.      protected Advised advised;  

10.     private Object[] constructorArgs;  

11.     private Class<?>[] constructorArgsTypes;  

12.     public CglibProxyFactory(Advised advised) throws AopConfigException {  

13.         if (advised.getAdvices().size() == 0) {  

14.             throw new AopConfigException("No advisors and no TargetSource specified");  

15.         }  

16.         this.advised = advised;  

17.     }  

18.     public void setConstructorArguments(Object[] constructorArgs, Class<?>[] constructorArgsTypes) {  

19.         if (constructorArgs == null || constructorArgsTypes == null) {  

20.             throw new IllegalArgumentException(  

21.                     "Both 'constructArgs' and 'constructorArgsTypes' can`t be null together");  

22.         }  

23.         if (this.constructorArgs.length != constructorArgsTypes.length) {  

24.             throw new IllegalArgumentException("Number of 'constructArgs' (" + constructorArgs.length  

25.                     + ") must match number of 'constructorArgsTypes' (" + constructorArgsTypes.length + ")");  

26.         }  

27.         this.constructorArgs = constructorArgs;  

28.         this.constructorArgsTypes = constructorArgsTypes;  

29.     }  

30.     @Override  

31.     public Object getProxy() {  

32.         return getProxy(null);  

33.     }  

34.     @Override  

35.     public Object getProxy(ClassLoader classLoader) {  

36.         if (log.isDebugEnabled()) {  

37.             log.debug("Creating CGLIB proxy: target source is " + this.advised.getTargetClass());  

38.         }  

39.         Class<?> rootClass = this.advised.getTargetClass();  

40.         Enhancer enhancer = new Enhancer();  

41.         if (classLoader != null) {  

42.             enhancer.setClassLoader(classLoader);  

43.         }  

44.         enhancer.setSuperclass(rootClass);  

45.         // 创建的代理类命名规则，默认后缀加上"BySpringCGLIB"  

46.         enhancer.setNamingPolicy(SpringNamingPolicy.INSTANCE);  

47.         enhancer.setInterceptDuringConstruction(false);  

48.         Callback[] callbacks = getCallbacks(rootClass);  

49.         Class<?>[] types = new Class<?>[callbacks.length];  

50.         for (int x = 0; x < callbacks.length; x++) {  

51.             types[x] = callbacks[x].getClass();  

52.         }  

53.         enhancer.setCallbackFilter(new ProxyCallbackFilter(this.advised));  

54.         enhancer.setCallbacks(callbacks);  

55.         enhancer.setCallbackTypes(types);  

56.         Object proxy;  

57.         if (this.constructorArgs != null) {  

58.             proxy = enhancer.create(constructorArgsTypes, constructorArgs);  

59.         } else {  

60.             proxy = enhancer.create();  

61.         }  

62.         return proxy;  

63.     }  

64.     private Callback[] getCallbacks(Class<?> rootClass) {  

65.         Callback aopInterceptor = new DynamicAdvisedInterceptor(this.advised);  

66.         Callback[] callbacks = new Callback[] { aopInterceptor };  

67.         return callbacks;  

68.     }  

69.     private static class DynamicAdvisedInterceptor implements MethodInterceptor, Serializable {  

70.         private final Advised advised;  

71.         public DynamicAdvisedInterceptor(Advised advised) {  

72.             super();  

73.             this.advised = advised;  

74.         }  

75.         @Override  

76.         public Object intercept(Object proxy, Method method, Object[] args, MethodProxy methodProxy) throws Throwable {  

77.             Class<?> targetClass = null;  

78.             Object target = this.advised.getTargetObject();  

79.             if (target != null) {  

80.                 targetClass = target.getClass();  

81.             }  

82.             List<Advice> chain = this.advised.getAdvices(method);  

83.             Object retVal;  

84.             if (chain.isEmpty() && Modifier.isPublic(method.getModifiers())) {  

85.                 retVal = methodProxy.invoke(target, args);  

86.             } else {  

87.                 List<org.aopalliance.intercept.MethodInterceptor> interceptors = new ArrayList<>();  

88.                 interceptors.addAll(chain);  

89.                 // 核心方法在这里  

90.                 retVal = new ReflectiveMethodInvocation(target, method, args, interceptors).proceed();  

91.             }  

92.             return retVal;  

93.         }  

94.     }  

95.     private static class ProxyCallbackFilter implements CallbackFilter {  

96.         private final Advised advised;  

97.         public ProxyCallbackFilter(Advised advised) {  

98.             this.advised = advised;  

99.         }  

100.         @Override  

101.         public int accept(Method method) {  

102.             return AOP_PROXY;  

103.         }  

104.     }  

105. }  
```



这里核心要关注的是getProxy()这个方法，怎么去获取代理类

首先声明被代理类

```
enhancer.setSuperclass(rootClass); 
```



其次声明拦截器

可以看到拦截器对被代理类的每个方法进行拦截，然后尝试获取method上的Advices，如果没有的话就直接调用，如果有的话就就运用到我们第三步的内容了，使用ReflectiveMethodInvocation有序调用拦截器链。

```
1.  private static class DynamicAdvisedInterceptor implements MethodInterceptor, Serializable {

2.     //...  

3.     @Override  

4.      public Object intercept(Object proxy, Method method, Object[] args, MethodProxy methodProxy) throws Throwable {  

5.      //...  

6.          List<Advice> chain = this.advised.getAdvices(method);  

7.          Object retVal;  

8.          if (chain.isEmpty() && Modifier.isPublic(method.getModifiers())) {  

9.              retVal = methodProxy.invoke(target, args);  

10.         } else {  

11.             List<org.aopalliance.intercept.MethodInterceptor> interceptors = new ArrayList<>();  

12.             interceptors.addAll(chain);  

13.             // 核心方法在这里  

14.             retVal = new ReflectiveMethodInvocation(target, method, args, interceptors).proceed();  

15.         }  

16.         return retVal;  

17.     }  

18. }  
```



最后声明过滤器

这里默认使用的就是aop的拦截器，其实Spring这里面还有很多其他的实现

```
1.  private static class ProxyCallbackFilter implements CallbackFilter {  

2.  //... 

3.      @Override  

4.      public int accept(Method method) {  

5.          return AOP_PROXY;  

6.      }  

7.  }  
```

现在一个指定类增强后的代理就完成了，调用Enhancer.create()可以生成一个类的代理类，调用这个类的所有方法都会经过代理类。



##### **（2）Jdk动态代理的实现**

jdk动态的实现相比较CGLIB来说简单一些，它只需要被代理的接口数组，然后声明一个InvocationHandler（反射调用的时候增强方法）

新增一个类JdkAopProxyFactory去做实现，相关代码如下：

```
1.  public class JdkAopProxyFactory implements AopProxyFactory, InvocationHandler {  

2.      private final Advised advised;  

3.      public JdkAopProxyFactory(Advised advised) throws AopConfigException {  

4.          if(advised.getAdvices().size() == 0) {  

5.              throw new AopConfigException("No advices specified");  

6.          }  

7.          this.advised = advised;  

8.      }  

9.      @Override  

10.     public Object getProxy() {  

11.         return getProxy(null);  

12.     }  

13.     @Override  

14.     public Object getProxy(ClassLoader classLoader) {  

15.         if(classLoader == null) {  

16.             classLoader = ClassUtils.getDefaultClassLoader();  

17.         }  

18.         Class<?>[] proxiedInterfaces =  advised.getProxiedInterfaces();  

19.         return Proxy.newProxyInstance(classLoader, proxiedInterfaces, this);  

20.     }  

21.     @Override  

22.     public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {  

23.         Object target = this.advised.getTargetObject();  

24.         //核心代理类的拦截方法  

25.         List<Advice> chain = this.advised.getAdvices(method);  

26.         Object retVal;  

27.         if (chain.isEmpty() && Modifier.isPublic(method.getModifiers())) {  

28.             retVal = method.invoke(target, args);  

29.         } else {  

30.             List<org.aopalliance.intercept.MethodInterceptor> interceptors = new ArrayList<>();  

31.             interceptors.addAll(chain);  

32.             // 核心方法在这里  

33.             retVal = new ReflectiveMethodInvocation(target, method, args, interceptors).proceed();  

34.         }  

35.         return retVal;  

36.     }     

37. }  
```

相关的增强方法的逻辑和CGLIB一样，就不多赘述了。



#### **5、总结**

1）使用CGLIB生成代理类时可以添加过滤器（过滤器需实现CallbackFilter接口）指定方法拦截器。

2）如何实现拦截器链的有序调用，Spring使用了一个很巧妙的递归方法。

3）学会了AspectJ里面一些方法的使用，比如expression转PointcutExpression这一块

4）进一步理解了Spring的开发理念，由点到面，一步步小功能可以实现一个比较大的概念。