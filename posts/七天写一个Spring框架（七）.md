七天写一个Spring框架（七）
2024-08-22
七天手写一个Spring轻量级框架之第七天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/356fe5244625f57dd4d395dfdf8baba1)



**今天的目标是**

完成Spring Aop的下半节，使满足aop配置的bean生成代理，在调用bean方法的时候去调用代理类的方法，从而实现增强



上一节我们已经可以根据Advised然后利用CglibProxyFactory去生成指定的代理类，使用起来类似于以下这种：

```
1.  @Test  

2.  public void testGetProxyClass() throws Throwable {  

3.      AdvisedSupport advised = new AdvisedSupport();  

4.      advised.addAdvice(beforeAdvice);  

5.      advised.addAdvice(afterAdvice);  

6.      advised.setTargetObject(personService);   

7.      CglibProxyFactory proxyFacotry = new CglibProxyFactory(advised);  

8.      PersonService personServiceProxy = (PersonService) proxyFacotry.getProxy();  

9.     // 这里personServiceProxy 已经是一个代理类了  

10.     personServiceProxy.placeOrder();  

11. }  
```



要实现我们最终的目标，需要思考的是

1）怎么获取所有的Advice？

2）是不是所有的bean都要生成代理类？

3）什么时候生成代理类？



#### **1、解析xml中的aop配置**

譬如给定一个aop配置如下：

```
1.  <aop:config>  

2.      <aop:aspect ref="tx">  

3.          <aop:pointcut expression="execution(* my_spring.beanfactory_aop2.test.service.*.placeOrder(..))" id="placeOrder"/>  

4.          <aop:before method="start" pointcut-ref="placeOrder"></aop:before>  

5.          <aop:after-throwing method="rollback" pointcut-ref="placeOrder"/>   

6.          <aop:after-returning method="commit" pointcut-ref="placeOrder"/>  

7.      </aop:aspect>  

8.  </aop:config>
```



我们是希望将<aop:before>转换成AspectJBeforeAdvice，将<aop:after-throwing>转换成AspectJAfterThrowingAdvice，将<aop:after-returning>转换成AspectJAfterAdvice，这样我们才可以将这些Advice放到Advised中去构建代理类

一开始我是以为直接转换成Advice相关类，然后存储到一个List中去，后面在getBean()的时候再一一比对

但是Spring不是这么做的，Spring引入了一个叫**人工合成BeanDefinition**（synthetic）的概念，可以理解成DTO的概念吧（把我们定义的Bean想象成DAO）

这里的目的就是将<aop:before>、<aop:after-throwing>、<aop:after-returning>甚至是<aop:pointcut>标签的信息都转换成人工合成的BeanDefinition

转换<aop:before>等advice的标签后的BeanDefinition如下所示

![img](http://pcc.huitogo.club/88c86f9eeb6c5210cea19176e6e268b4)



根据上图我们适当修改AbstractAspectJAdvice的构造函数，也就是Advice接口的模板类，使它扩展性更高

```
1.  public abstract class AbstractAspectJAdvice implements Advice {  

2.      private Method adviceMethod;  

3.      private AspectJExpressionPointcut pointcut;  

4.      private AspectInstanceFactory adviceObjectFactory;  

5.  //修改了构造方法第二和第三个参数

6.      public AbstractAspectJAdvice(Method adviceMethod, AspectJExpressionPointcut pointcut, AspectInstanceFactory adviceObjectFactory) {  

7.          super();  

8.          this.adviceMethod = adviceMethod;  

9.          this.pointcut = pointcut;  

10.         this.adviceObjectFactory = adviceObjectFactory;  

11.     }  

12.     public void invokeAdviceMethod() throws Throwable {  

13.         adviceMethod.invoke(adviceObjectFactory.getAspectBean());  

14.     }  

15.     //...  

16. }  
```



构造函数里面的**AspectInstanceFactory**类，这个类用来处理切面的信息，相关代码：

```
1.  public class AspectInstanceFactory implements BeanFactoryAware {  

2.     // 切面的beanName

3.      private String aspectBeanName;  

4.      private AbstractBeanFactory beanFactory;  

5.      public void setAspectBeanName(String aspectBeanName) {  

6.          this.aspectBeanName = aspectBeanName;  

7.      }  

8.      public Object getAspectBean() {  

9.          return beanFactory.getBean(aspectBeanName);  

10.     }  

11.     @Override  

12.     public void setBeanFactory(BeanFactory beanFactory) {  

13.         this.beanFactory = (AbstractBeanFactory) beanFactory;  

14.     }  

15.     public Object getAspectInstance() {  

16.         return this.beanFactory.getBean(this.aspectBeanName);  

17.     }  

18. }  
```



同时修改一下我们上一节用来定位切面方法的**MethodLocatingFactory**，将它的getObject()和setBeanFactory()方法抽象出来

```
1.  public class MethodLocatingFactory implements FactoryBean<Method>, BeanFactoryAware{  

2.      ...  

3.  }  

4.  public interface FactoryBean<T> {  

5.      T getObject() throws Exception;  

6.      Class<?> getObjectType();  

7.  }  

8.  public interface BeanFactoryAware {  

9.       void setBeanFactory(BeanFactory beanFactory);  

10. }  
```

这里要注意以下FactoryBean和BeanFactory的区别，**BeanFactory是用来获取Bean的，相当于生产工厂，FactoryBean是用来对Bean进行转换的，相当于加工工厂**。



下一步就是将pointcut的标签转换成BeanDefinition，如下所示

![img](http://pcc.huitogo.club/bdb0b4a4f76d6041c939511244be3365)



我们在XmlBeanDefinitionReader.loadBeanDefinition()中对aop标签进行解析

```
1.  public void loadBeanDefinition(Resource resource) {  

2.      //...  

3.          while (itr.hasNext()) {  

4.              Element ele = itr.next();  

5.              String namespaceUri = ele.getNamespaceURI();  

6.              // 判断标签的命名空间  

7.              if (isDefaultNamespace(namespaceUri)) {  

8.                  parseDefaultElement(ele);  

9.              } else if (isContextNamespace(namespaceUri)) {  

10.                 parseComponentElement(ele);  

11.             }else if(isAOPNamespece(namespaceUri)) {  

12.                 parseAopElement(ele);  

13.             }  

14.         }  

15.         //...  

16. }  

17. private void parseAopElement(Element ele) {  

18.     ConfigBeanDefinitionParser parser = new ConfigBeanDefinitionParser();  

19.     parser.parse(ele, this.registry);  

20. }  
```



具体的解析过程在ConfigBeanDefinitionParser.parse()中，ConfigBeanDefinitionParser代码如下：

```
1.  public class ConfigBeanDefinitionParser {  

2.     //相关标签名称

3.      private static final String ASPECT = "aspect";  

4.      private static final String ID = "id";  

5.      private static final String REF = "ref";  

6.      private static final String AFTER = "after";  

7.      private static final String AFTER_RETURNING_ELEMENT = "after-returning";  

8.      private static final String AFTER_THROWING_ELEMENT = "after-throwing";  

9.      private static final String AROUND = "around";  

10.     private static final String BEFORE = "before";  

11.     private static final String POINTCUT = "pointcut";  

12.     private static final String ASPECT_NAME_PROPERTY = "aspectName";  

13.     private static final String POINTCUT_REF = "pointcut-ref";  

14.     private static final String EXPRESSION = "expression";  


15.     public BeanDefinition parse(Element ele, BeanDefinitionRegistry registry) {  

16.         List<Element> childElts = ele.elements();  

17.         for (Element childElem : childElts) {  

18.             String localName = childElem.getName();  

19.             if (ASPECT.equals(localName)) {  

20.                 parseAspect(childElem, registry);  

21.             }  

22.         }  

23.         return null;  

24.     }  


25.     //解析<aspect标签>  

26.     private void parseAspect(Element aspectElement, BeanDefinitionRegistry registry) {  

27.         String aspectName = aspectElement.attributeValue(REF);  

28.         List<BeanDefinition> beanDefinitions = new ArrayList<>();  

29.         List<RuntimeBeanReference> beanReferences = new ArrayList<>();  

30.         List<Element> eleList = aspectElement.elements();  

31.         // 是否已经添加new RuntimeBeanReference(aspectName)  

32.         // 只有在有AdviceNode的时候这个beanReferences添加了才有意义  

33.         boolean adviceFoundAlready = false;  

34.         for (int i = 0; i < eleList.size(); i++) {  

35.             Element ele = eleList.get(i);  

36.             if (isAdviceNode(ele)) {  

37.                 if (!adviceFoundAlready) {  

38.                     adviceFoundAlready = true;  

39.                     if (!StringUtils.hasText(aspectName)) {  

40.                         return;  

41.                     }  

42.                     beanReferences.add(new RuntimeBeanReference(aspectName));  

43.                 }  

44.                 GenericBeanDefinition advisorDefinition = parseAdvice(aspectName, i, aspectElement, ele, registry, beanDefinitions, beanReferences);  

45.                 beanDefinitions.add(advisorDefinition);  

46.             }  

47.         }  

48.         List<Element> pointcuts = aspectElement.elements(POINTCUT);  

49.         for (Element pointcutElement : pointcuts) {  

50.             parsePointcut(pointcutElement, registry);  

51.         }  

52.     }  


53.     //解析<aop:before>等advice类型的标签  

54.     private GenericBeanDefinition parseAdvice(String aspectName, int order, Element aspectElement,  Element adviceElement, BeanDefinitionRegistry registry, List<BeanDefinition> beanDefinitions, List<RuntimeBeanReference> beanReferences) {  

55.         GenericBeanDefinition methodDefinition = new GenericBeanDefinition(MethodLocatingFactory.class);  

56.         methodDefinition.getPropertyValues().add(new PropertyValue("targetBeanName", aspectName));  

57.         methodDefinition.getPropertyValues().add(new PropertyValue("methodName", adviceElement.attributeValue("method")));  

58.         methodDefinition.setSynthetic(true);  

59.         GenericBeanDefinition aspectFactoryDef = new GenericBeanDefinition(AspectInstanceFactory.class);  

60.         aspectFactoryDef.getPropertyValues().add(new PropertyValue("aspectBeanName", aspectName));  

61.         aspectFactoryDef.setSynthetic(true);  

62.  GenericBeanDefinition adviceDef = createAdviceDefinition(adviceElement, registry, aspectName, order,  methodDefinition, aspectFactoryDef, beanDefinitions, beanReferences);  

63.         adviceDef.setSynthetic(true);  

64.         BeanDefinitionReaderUtils.registerWithGeneratedName(adviceDef, registry);  

65.         return null;  

66.     }  


67.     //解析<aop:point>标签  

68.     private GenericBeanDefinition parsePointcut(Element pointcutElement, BeanDefinitionRegistry registry) {  

69.         String id = pointcutElement.attributeValue(ID);  

70.         String expression = pointcutElement.attributeValue(EXPRESSION);  

71.         GenericBeanDefinition pointcutDefinition = null;  

72.         pointcutDefinition = createPointcutDefinition(expression);  

73.         String pointcutBeanName = id;  

74.         if (StringUtils.hasText(pointcutBeanName)) {  

75.             registry.registryBeanDefinition(pointcutBeanName, pointcutDefinition);  

76.         } else {  

77.             BeanDefinitionReaderUtils.registerWithGeneratedName(pointcutDefinition, registry);  

78.         }  

79.         return pointcutDefinition;  

80.     }  


81.     //ele是不是<aop:before>等类型advice的标签  

82.     private boolean isAdviceNode(Element ele) {  

83.         if (!(ele instanceof Element)) {  

84.             return false;  

85.         } else {  

86.             String name = ele.getName();  

87.             return (BEFORE.equals(name) || AFTER.equals(name) || AFTER_RETURNING_ELEMENT.equals(name) || AFTER_THROWING_ELEMENT.equals(name) || AROUND.equals(name));  

88.         }  

89.     }  


90.     //创建Advice对应的BeanDefinition  

91.     private GenericBeanDefinition createAdviceDefinition(Element adviceElement, BeanDefinitionRegistry registry, String aspectName, int order, GenericBeanDefinition methodDefinition,  GenericBeanDefinition aspectFactoryDef, List<BeanDefinition> beanDefinitions, List<RuntimeBeanReference> beanReferences) {  

92.         GenericBeanDefinition adviceDefinition = new GenericBeanDefinition(getAdviceClass(adviceElement));  

93.         adviceDefinition.getPropertyValues().add(new PropertyValue(ASPECT_NAME_PROPERTY, aspectName));  

94.         // 构建adviceDefinition的构造函数  

95.         ConstructorArgument cav = adviceDefinition.getConstructorArgument();  

96. //第一个构造参数MethodLocatingFactory

97.         cav.addArgumentValue(new ValueHolder(methodDefinition));  

98.    //第二个构造参数 AspectJExpressionPointcut

99.         Object pointcut = parsePointProperty(adviceElement);  

100.         if (pointcut instanceof BeanDefinition) {  

101.             cav.addArgumentValue(new ValueHolder(pointcut));  

102.         } else if (pointcut instanceof String) {  

103.             RuntimeBeanReference pointcutRef = new RuntimeBeanReference((String) pointcut);

104.             beanReferences.add(pointcutRef);  

105.             cav.addArgumentValue(new ValueHolder(pointcutRef));  

106.         }  

107. //第三个构造参数AspectInstanceFactory

108.         cav.addArgumentValue(new ValueHolder(aspectFactoryDef));  

109.         return adviceDefinition;  

110.     }  


111.     //解析<aop:pointcut>标签的属性  

112.     private Object parsePointProperty(Element adviceElement) {  

113.         if (adviceElement.attribute(POINTCUT) != null && adviceElement.attribute(POINTCUT_REF) != null) {  

114.             return null;  

115.         } else if (adviceElement.attribute(POINTCUT) != null) {  

116.             String expression = adviceElement.attributeValue(POINTCUT);  

117.             GenericBeanDefinition pointcutDefinition = createPointcutDefinition(expression);

118.             return pointcutDefinition;  

119.         }else if (adviceElement.attribute(POINTCUT_REF) != null) {  

120.             String pointcutRef = adviceElement.attributeValue(POINTCUT_REF);  

121.             if (!StringUtils.hasText(pointcutRef)) {  

122.                 return null;  

123.             }  

124.             return pointcutRef;  

125.         } else {  

126.             return null;  

127.         }  

128.     }  


129.     //创建pointcut的BeanDefinition  

130.     private GenericBeanDefinition createPointcutDefinition(String expression) {  

131.         GenericBeanDefinition beanDefinition = new GenericBeanDefinition(AspectJExpressionPointcut.class);  

132.         beanDefinition.setScope(BeanDefinition.SCOPE_PROTOTYPE);  

133.         beanDefinition.setSynthetic(true);  

134.        beanDefinition.getPropertyValues().add(new PropertyValue(EXPRESSION, expression));  

135.         return beanDefinition;  

136.     }  


137.     //判断adviceElement标签的advice类型  

138.     private Class<?> getAdviceClass(Element adviceElement) {  

139.         String elementName = adviceElement.getName();  

140.         if (BEFORE.equals(elementName)) {  

141.             return AspectJBeforeAdvice.class;  

142.         } else if (AFTER_RETURNING_ELEMENT.equals(elementName)) {  

143.             return AspectJAfterAdvice.class;  

144.         } else if (AFTER_THROWING_ELEMENT.equals(elementName)) {  

145.             return AspectJAfterThrowingAdvice.class;  

146.         } else {  

147.             return null;  

148.         }  

149.     }  

150. }  
```



这是一段冗长的代码，主要的任务就是解析<aop:config>标签里面的<aop:aspect>标签



来看一下任务相关的代码

**解析<aop:pointcut>标签为BeanDefinition并registry到BeanFactory中**

```
1.  private GenericBeanDefinition parsePointcut(Element pointcutElement, BeanDefinitionRegistry registry) {  

2.      //...  

3.      GenericBeanDefinition pointcutDefinition = createPointcutDefinition(expression);  

4.      //...  

5.      registry.registryBeanDefinition(pointcutBeanName, pointcutDefinition);  

6.      //...  

7.      return pointcutDefinition;  

8.  }  


9.  private GenericBeanDefinition createPointcutDefinition(String expression) {  

10.     GenericBeanDefinition beanDefinition = new GenericBeanDefinition(AspectJExpressionPointcut.class);  

11.     beanDefinition.setScope(BeanDefinition.SCOPE_PROTOTYPE);  

12.     beanDefinition.setSynthetic(true);  

13.     beanDefinition.getPropertyValues().add(new PropertyValue(EXPRESSION, expression));  

14.     return beanDefinition;  

15. }  
```



**解析<aop:before>等Advice标签为BeanDefinition并registry到BeanFactory中**

先要生成Advice构造函数中的两个GenericBeanDefinition参数，对应的类是MethodLocatingFactory和AspectInstanceFactory

```
1.  private GenericBeanDefinition parseAdvice(String aspectName, int order, Element aspectElement, Element adviceElement, BeanDefinitionRegistry registry, List<BeanDefinition> beanDefinitions, List<RuntimeBeanReference> beanReferences) {  

2.      GenericBeanDefinition methodDefinition = new GenericBeanDefinition(MethodLocatingFactory.class);  

3.      methodDefinition.getPropertyValues().add(new PropertyValue("targetBeanName", aspectName));  

4.      methodDefinition.getPropertyValues().add(new PropertyValue("methodName", adviceElement.attributeValue("method")));  

5.      methodDefinition.setSynthetic(true);  

6.      GenericBeanDefinition aspectFactoryDef = new GenericBeanDefinition(AspectInstanceFactory.class);  

7.      aspectFactoryDef.getPropertyValues().add(new PropertyValue("aspectBeanName", aspectName));  

8.      aspectFactoryDef.setSynthetic(true);  

9.      GenericBeanDefinition adviceDef = createAdviceDefinition(adviceElement, registry, aspectName, order, methodDefinition, aspectFactoryDef, beanDefinitions, beanReferences);  

10.     adviceDef.setSynthetic(true);  

11.     BeanDefinitionReaderUtils.registerWithGeneratedName(adviceDef, registry);  

12.     return null;  

13. }  
```



再创建这个Advice的BeanDefinition，主要任务花在合成这个BeanDefinition的ConstructorArgument

```
1.  private GenericBeanDefinition createAdviceDefinition(Element adviceElement, BeanDefinitionRegistry registry, String aspectName, int order, GenericBeanDefinition methodDefinition, GenericBeanDefinition aspectFactoryDef, List<BeanDefinition> beanDefinitions,  List<RuntimeBeanReference> beanReferences) {  

2.      GenericBeanDefinition adviceDefinition = new GenericBeanDefinition(getAdviceClass(adviceElement));  

3.      adviceDefinition.getPropertyValues().add(new PropertyValue(ASPECT_NAME_PROPERTY, aspectName));  

4.      // 构建adviceDefinition的构造函数  

5.      ConstructorArgument cav = adviceDefinition.getConstructorArgument();  

6.  //第一个构造参数MethodLocatingFactory

7.      cav.addArgumentValue(new ValueHolder(methodDefinition));  

8.  //第二个构造参数 AspectJExpressionPointcut

9.      Object pointcut = parsePointProperty(adviceElement);  

10.     if (pointcut instanceof BeanDefinition) {  

11.         cav.addArgumentValue(new ValueHolder(pointcut));  

12.     } else if (pointcut instanceof String) {  

13.         RuntimeBeanReference pointcutRef = new RuntimeBeanReference((String) pointcut);  

14.         beanReferences.add(pointcutRef);  

15.         cav.addArgumentValue(new ValueHolder(pointcutRef));  

16.     }  

17. // 第三个构造参数AspectInstanceFactory

18.     cav.addArgumentValue(new ValueHolder(aspectFactoryDef));  

19.     return adviceDefinition;  

20. }  
```

至此<aop:before>等advice标签的BeanDefinition就被我们创建完毕并registry到BeanFactory中去



有个需要注意的就是在Advice的模板类AbstractAspectJAdvice中的构造函数第一个是Method，而我们这里第一个构造函数是MethodLocatingFactory（FactoryBean）类的BeanDefinition，所以在BeanDefinitionValueResolver解析的时候需要添加一项对类型是BeanDefinition的处理，

相关代码如下：

```
1.  public class BeanDefinitionValueResolver {  

2.      public Object resolveValueIfNecessary(Object value) {  

3.          if (value instanceof RuntimeBeanReference) {  

4.  //...  

5.          } else if (value instanceof TypedStringValue) {  

6.  //...  

7.          } else if (value instanceof BeanDefinition) {  

8.              BeanDefinition bd = (BeanDefinition) value;  

9.              String innerBeanName = "(inner bean)" + bd.getClassName() + "#"  

10.                     + Integer.toHexString(System.identityHashCode(bd));  

11.             return resolveInnerBean(innerBeanName, bd);  

12.         } else if (value instanceof String) {  

13. //...  

14.         } else {  

15. //...  

16.         }  

17.     }  


18.     private Object resolveInnerBean(String innerBeanName, BeanDefinition bd) {  

19.         Object innerBean = this.defaultBeanFactory.createBean(bd);  

20.         if (innerBean instanceof FactoryBean) {  

21.             try {  

22.                 return ((FactoryBean) innerBean).getObject();  

23.             } catch (Exception e) {}  

24.         } else {  

25.             return innerBean;  

26.         }  

27.     }  

28. }  
```

就是调用了一下FactoryBean的getObject()方法，对这个BeanDefinition进行了转换。



#### **2、在Bean初始化的时候生成代理类**

我们再来看一下Bean的生命周期，如下图

![img](http://pcc.huitogo.club/2c269631f633da39d566bfa20a49ed97)

很明显，**一个类是否生成代理类应该在它实例化之前去做**，所以我们可以等这个类在初始化后（拥有基本属性和方法了）再去判断是否生成它的代理类



所以我们新增一个类**AspectJAutoProxyCreater**去实现**BeanPostProcessor**（初始化接口）接口，在afterInitialization()中去做这件事，相关代码如下：

```
1.  public class AspectJAutoProxyCreater implements BeanPostProcessor {  

2.      AbstractBeanFactory beanFactory;  

3.      public void setBeanFactory(AbstractBeanFactory beanFactory) {  

4.          this.beanFactory = beanFactory;  

5.      }  

6.      @Override  

7.      public Object beforeInitialization(Object bean, String beanName) throws BeanException {

8.          return bean;  

9.      }  

10.     @Override  

11.     public Object afterInitialization(Object bean, String beanName) throws BeanExceptionn {

12.         // 如果这个类本身就是Advice及其子类，那就不要生成动态代理了  

13.         if (isInfrastrureClass(bean.getClass())) {  

14.             return bean;  

15.         }  

16.         List<Advice> advices;  

17.         try {  

18. //获取bean中可用的Advice

19.             advices = getCadidateAdvices(bean);  

20.             if (advices.isEmpty()) {  

21.                 return bean;  

22.             }  

23.             return createProxy(advices, bean);  

24.         } catch (NoSuchBeanDefinitionException e) {  

25.             return null;  

26.         }  

27.     }  

28.     /** 

29.      * 根据advices拦截器链创建bean的代理类 

30.      * @param advices 

31.      * @param bean 

32.      * @return 

33.      */  

34.     private Object createProxy(List<Advice> advices, Object bean) {  

35.         AdvisedSupport advised = new AdvisedSupport();  

36.         for (Advice advice : advices) {  

37.             advised.addAdvice(advice);  

38.         }  

39.    //jdk动态代理需要的父类接口数组

40.         Set<Class<?>> targetInterfaces = ClassUtils.getAllInterfacesForClassAsSet(bean.getClass());  

41.         for (Class<?> clazz : targetInterfaces) {  

42.             advised.addInterface(clazz);  

43.         }  

44.         advised.setTargetObject(bean);  

45.         AopProxyFactory proxyFactory = null;  

46.         try {  

47.             // 如果targetBean没有接口的话就使用CGLIB生成代理  

48.             if (advised.getProxiedInterfaces().length == 0) {  

49.                 proxyFactory = new CglibProxyFactory(advised);  

50.             // 有接口就使用jdk动态代理  

51.             } else {  

52.                 proxyFactory = new JdkAopProxyFactory(advised);  

53.             }  

54.             return proxyFactory.getProxy();  

55.         } catch (AopConfigException e) {  

56.             return null;  

57.         }  

58.     }  

59.     private List<Advice> getCadidateAdvices(Object bean) throws NoSuchBeanDefinitionException {  

60.         List<Object> advices = this.beanFactory.getBeansByType(Advice.class);  

61.         List<Advice> result = new ArrayList<>();  

62.         for (Object advice : advices) {  

63.             Pointcut pc = ((Advice) advice).getPointcut();  

64.             if (canApply(pc, bean.getClass())) {  

65.                 result.add((Advice) advice);  

66.             }  

67.         }  

68.         return result;  

69.     }  

70.     /** 

71.      * 判断targetClass有没有方法满足pc表达式 

72.      * @param pc 

73.      * @param targetClass 

74.      * @return 

75.      */  

76.     private boolean canApply(Pointcut pc, Class<? extends Object> targetClass) {  

77.         MethodMatcher methodMatcher = pc.getMethodMatcher();  

78.        Set<Class> classes = new LinkedHashSet<>(ClassUtils.getAllInterfacesForClassAsSet(targetClass));  

79.         classes.add(targetClass);  

80.         for (Class<?> clazz : classes) {  

81.             Method[] methods = clazz.getDeclaredMethods();  

82.             for (Method method : methods) {  

83.                 if (methodMatcher.match(method)) {  

84.                     return true;  

85.                 }  

86.             }  

87.         }  

88.         return false;  

89.     }  

90.     /** 

91.      * 判断beanClass是不是Advice的子类 

92.      * @param beanClass 

93.      * @return 

94.      */  

95.     private boolean isInfrastrureClass(Class<? extends Object> beanClass) {  

96.         boolean retVal = Advice.class.isAssignableFrom(beanClass);  

97.         return retVal;  

98.     }  

99. }  
```

这里就是在BeanPostProcessor的afterInitialization（初始化后）方法中去判断当前是否需要生成代理，以及用什么样的方式去生成代理。



上面的步骤解释如下：

先判断这个Bean里面有没有method满足Advice的PointcutExpression

在有Advice的情况下，根据这个Bean有没有实现接口去判断使用CGLIB还是JDK动态代理去生成Bean的代理对象。

这里就运用到我们上一节的**CglibProxyFactory**和**JdkAopProxyFactory**

```
1.  if (advised.getProxiedInterfaces().length == 0) {  

2.      proxyFactory = new CglibProxyFactory(advised);  

3.      // 有接口就使用jdk动态代理  

4.  } else {  

5.      proxyFactory = new JdkAopProxyFactory(advised);  

6.  }  

7.  return proxyFactory.getProxy();  
```



做好这件事后我们回到DefaultBeanFactory中去添加Bean初始化时操作（BeanPostProcessor接口下的实现类）

```
1.  public class DefaultBeanFactory extends AbstractBeanFactory implements BeanDefinitionRegistry {  

2.  //...

3.  //Bean的初始化   

4.   protected Object createBean(BeanDefinition bd) {  

5.          // 初始化Bean  

6.          Object bean = initalBean(bd);  

7.          // 给bean设置属性  

8.          populateBean(bd, bean);  

9.          // 对于BeanFactoryAware接口的Bean设置BeanFactory  

10.         // 是否生成代理类  

11.         bean = initalizeBean(bd, bean);  

12.         return bean;  

13.     }  

14.     protected Object initalizeBean(BeanDefinition bd, Object bean) {  

15.         invokeAwareMethods(bean);  

16.         //是否人工合成的BeanDefinition  

17.         if(!bd.isSynthetic()) {   

18.             // 创建Bean的代理类  

19.             return applyBeanPostProcessorAfterInitalization(bean, bd.getId());  

20.         }  

21.         return bean;  

22.     }  

23.     private void invokeAwareMethods(final Object bean) {  

24.         if(bean instanceof BeanFactoryAware) {  

25.             ((BeanFactoryAware) bean).setBeanFactory(this);  

26.         }  

27.     }  

28.     //调用bean生命周期中初始化的过程  

29.     private Object applyBeanPostProcessorAfterInitalization(Object existingBean, String beanName) {  

30.         Object result = existingBean;  

31.         for(BeanPostProcessor beanPostProcessor : getBeanPostProcessor()) {  

32. //这里调用bean初始化后的方法

33.             result = beanPostProcessor.afterInitialization(result, beanName);  

34.             if(result == null) {  

35.                 return result;  

36.             }  

37.         }  

38.         return result;  

39.     }  

40. }  
```

这样我们就在bean初始化后判断是否生成Bean代理类，顺便还将继承了BeanFactoryAware的Bean（这里指人工合成的Bean）设置了一下BeanFactory，Perfect！



#### **3、总结**

1）相比较来说，解析xml生成Advice对象这个过程还是比较复杂的，核心是将<aop:before>转换成BeanDefinition<AspectJBeforeAdvice>，需要考虑的就是它的List<Property>和ConstructorArgument怎么构建，需要什么就去补什么，但是典型的由大化小的思想。

2）进一步理解了Bean的生命以及在Spring中的体现，实现了BeanPostProcessor的类可以在Bean初始化中做一些事情，实现了InstantiationAwareBeanPostProcessor的接口可以在Bean实例化中做一些事情，等等。

3）理解了BeanFactory和FactoryBean的区别，两个都是SpringBean中重要的接口，BeanFactory是Bean的生产车间，FactoryBean是Bean的转换车间。

4）jdk动态代理和Cglib在SpringAop中都有应用，因为两者各有优劣势，比如没有实现任何接口的类只能用CGLIB来实现，有接口的类用jdk动态代理实现，因为jdk动态创建代理速度更快。