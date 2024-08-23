七天写一个Spring框架（三）
2024-08-22
七天手写一个Spring轻量级框架之第三天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/1deb436961a7ef6ecde535bb25b24fa5)



今天的目标也是

获取bean的属性值和引用对象，但不同于上节，上节讲的通过bean的get +属性名和xml配置<property>标签中的name相对应进行匹配和赋值操作，这节复杂一点，我们通过bean的构造函数中的参数和xml中的<constuct-arg>标签进行对应和赋值操作。



在xml中如下所示

```
1.  <bean id = "personService" class="my_spring.beanfactory_construt.test.service.PersonService">  

2.      <constructor-arg index="2" ref="drinkDao" />  

3.      <constructor-arg name="eatDao" ref="eatDao" />  

4.      <constructor-arg index="3" type="java.lang.String" value="zhanghui" />  

5.      <constructor-arg index="4" type="java.lang.Integer" value="18" />  

6.  </bean>  
```



编写出来的成功测试用例跟上节一样

```
1.  @Test  

2.  public void testGetBeanProperties() {  

3.      ApplicationContext context = new ClassPathXmlApplicationContext("applicationContext.xml");  

4.      PersonService personService = (PersonService) context.getBean("personService");  

5.      Assert.notNull(personService.getEatDao());  

6.      Assert.notNull(personService.getDrinkDao());  

7.      assertTrue("zhanghui".equals(personService.getName()));  

8.      assertTrue(personService.getAge() == 18);  

9.  }  
```

既然本节目标跟上节目标一致，自然设计思路也差不多



#### **1、第一步**

在xml解析的时候将<bean>标签中<construct-arg>列表抽象出来放到对应的Beandefinition中去

我们新增一个对象**ConstructorArgument**来存储<construct-arg>标签列表

```
1.  public class ConstructorArgument {  

2.      private List<ValueHolder> argumentValues = new LinkedList<>();  

3.      public List<ValueHolder> getArgumentValues() {  

4.          return Collections.unmodifiableList(argumentValues);  

5.      }  

6.      public void addArgumentValue(ValueHolder valueHolder) {  

7.          this.argumentValues.add(valueHolder);  

8.      }  

9.      public int getArgumentCount() {  

10.         return argumentValues.size();  

11.     }  

12.     public boolean isEmpty() {  

13.         return this.argumentValues.isEmpty();  

14.     }  


15.     // 对应一个<construct-arg>  

16.     @Data  

17.     @NoArgsConstructor  

18.     public static class ValueHolder {  

19.         private Object value;  

20.         private String type;  

21.         private String name;  

22.         private int index;  

23.         public ValueHolder(Object value) {  

24.             this.value = value;  

25.         }  

26.     }  

27. }  
```



在BeanDefinition接口中定义操作ConstructorArgument的方法

```
1.  public interface BeanDefinition {  

2.      //...  

3.      ConstructorArgument getConstructorArgument();  

4.      boolean hasConstructorArgumentValues();  

5.  }  
```



在GenericBeanDefinition中实现

```
1.  @Data  

2.  public class GenericBeanDefinition implements BeanDefinition {  

3.      public ConstructorArgument constructorArgument = new ConstructorArgument();  

4.      @Override  

5.      public boolean hasConstructorArgumentValues() {  

6.          return !this.constructorArgument.isEmpty();  

7.      }  

8.  } 
```



#### **2、第二步**

这个时候BeanDefinition里面已经有了construct-arg列表了，而且可以获取到bean实例，那么怎么将<construct-arg>标签属性放到ConstructorArgument的ValueHolder中呢？

思路就是**在bean实例中找到对应<construct-arg>标签列表的构造函数**

比如construct-arg列表是下面这个

```
1.  <bean id = "personService" class="my_spring.beanfactory_construt.test.service.PersonService">  

2.      <constructor-arg index="1" name="eatDao" ref="eatDao" />  

3.      <constructor-arg index="2" ref="drinkDao" />  

4.      <constructor-arg index="3" type="java.lang.String" value="zhanghui" />  

5.      <constructor-arg index="4" type="java.lang.Integer" value="18" />  

6.  </bean>
```



对应的构造函数就应该是这样

```
1.  public PersonService(EatDao eatDao, DrinkDao drinkDao, String name, int age) {  

2.      super();  

3.      this.eatDao = eatDao;  

4.      this.drinkDao = drinkDao;  

5.      this.name = name;  

6.      this.age = age;  

7.  } 
```



我们定义**ConstructorResolver**去做这件事情，用代码实现如下：

```
1.  public class ConstructorResolver {  

2.      protected final Logger log = LoggerFactory.getLogger(ConstructorResolver.class);  

3.      private final ConfigurableBeanFactory beanFactory;  

4.      public ConstructorResolver(ConfigurableBeanFactory beanFactory) {  

5.          super();  

6.          this.beanFactory = beanFactory;  

7.      }  


8.      /** 

9.       * 根据xml中配置的construct-arg列表，找到bd对应类中最合适的构造函数进行关联 

10.      */  

11.     public Object autowiredConstructor(BeanDefinition bd) {  

12.         // 匹配成功后对应的构造函数  

13.         Constructor<?> constructorToUse = null;  

14.         // 用来存放将ConstructorArgument中的argumentValues进行

15.         BeanDefinitionValueResolver.resolveValueIfNecessary转换后的值  

16.         Object[] argsToUse = null;  

17.         Class<?> beanClass = null;  

18.         try {  

19.             beanClass = this.beanFactory.getClassLoader().loadClass(bd.getClassName());  

20.             Constructor<?>[] candidates = beanClass.getDeclaredConstructors();  

21.             BeanDefinitionValueResolver valueResolver = new BeanDefinitionValueResolver(this.beanFactory);  

22.             ConstructorArgument args = bd.getConstructorArgument();  

23.             SimpleTypeConverter typeConverter = new SimpleTypeConverter();  

24.             // 获取构造函数的参数名称  

25.             LocalVariableTableParameterNameDiscoverer parameterNameDiscoverer = new LocalVariableTableParameterNameDiscoverer();  

26.             for (int i = 0; i < candidates.length; i++) {  

27.                 Parameter param[] = candidates[i].getParameters();  

28.                 String[] paramsName = parameterNameDiscoverer.getParameterNames(candidates[i]);  

29. //先对参数长度进行判断

30.                 if (param.length != args.getArgumentCount()) {  

31.                     continue;  

32.                 }  

33.                 argsToUse = new Object[param.length];  

34.                 // 进行类型匹配  

35.                 boolean result = this.valueMatchTypes(param, paramsName, args.getArgumentValues(), argsToUse, valueResolver, typeConverter);  

36.                 if (result) {  

37.                     constructorToUse = candidates[i];  

38.                     break;  

39.                 }  

40.             }  

41.             if (constructorToUse == null) {  

42.                 throw new BeanCreateException(bd.getId(), "can`t find  a apporiate constructor");  

43.             }  

44.             try {  

45. //找到匹配的构造函数后，直接根据<construct-arg>标签列表的值进行实例化

46.                 return constructorToUse.newInstance(argsToUse);  

47.             } catch (Exception e) {  

48.                 throw new BeanCreateException(bd.getId(), "can`t find  a create instance using" + argsToUse);  

49.             }  

50.         } catch (ClassNotFoundException e) {  

51.             e.printStackTrace();  

52.         }  

53.         return null;  

54.     }  

55. }  
```



上述过程就是遍历出bean实例的所有构造函数

```
Constructor<?>[] candidates = beanClass.getDeclaredConstructors(); 
```

进行类型匹配

```
boolean result = this.**valueMatchTypes**(param, paramsName, args.getArgumentValues(), argsToUse, valueResolver, typeConverter); 
```

匹配成功根据construct-arg列表给的值实例化bean

```
return constructorToUse.newInstance(argsToUse); 
```



这里重点是valueMatchTypes这个匹配方法

鉴于ValueHolder属性也就是<construct-arg>标签中的属性有index、name、type

那么就基于这三个维度去做过滤，当然第一道过滤是判断参数个数不用说

对应valueMatchTypes如下

```
1. private boolean valueMatchTypes(Parameter[] params, String[] paramsName, List<ValueHolder> argumentValues, Object[] argsToUse, BeanDefinitionValueResolver valueResolver, SimpleTypeConverter typeConverter) throws ClassNotFoundException {  

2.      //根据index排序  

3.      argumentValues = countSort(argumentValues);  

4.      for (int i = 0; i < params.length; i++) {  

5.          ConstructorArgument.ValueHolder valueHolder = argumentValues.get(i);  

6.          //判断名称name  

7.          if (StringUtils.isNotBlank(valueHolder.getName())) {  

8.              if (!StringUtils.equals(paramsName[i], valueHolder.getName())) {  

9.                  return false;  

10.             }  

11.         }  

12.         //判断类型type  

13.         if (StringUtils.isNotBlank(valueHolder.getType())) {  

14.             Class valueClazz = Class.forName(valueHolder.getType());  

15.             if (!ClassUtils.isAssignable(valueClazz, params[i].getType())) {  

16.                 return false;  

17.             }  

18.         }  

19.         // 默认进行类型匹配  

20.         try {  

21.             Object resolveValue = valueResolver.resolveValueIfNecessary(valueHolder.getValue());  

22.             // 核心在这里，如果不能将argumentValues中的值转换成parameterTypes中对应的类，则转型失败，类型不匹配  

23.             Object convertedValue = typeConverter.convertIfNecessary(resolveValue, params[i].getType());  

24.             // 转型成功，记录下来  

25.             argsToUse[i] = convertedValue;  

26.         } catch (TypeMismatchException e) {  

27.             log.error(e.getMessage());  

28.             return false;  

29.         } catch (RuntimeException e) {  

30.             log.error(e.getMessage());  

31.             return false;  

32.         }  

33.     }  

34.     return true;  

35. }  
```



上述过程就是

1）先给construct-arg根据index排序，这里有个细节就是不能打乱默认顺序，比如两个index都是0（默认）的construct-arg不能在排序后打乱先后顺序

排序算法如下，注意这里用的是 >=

```
1.  private List<ValueHolder> countSort(List<ValueHolder> argumentValues) {  

2.      List<ValueHolder> result = argumentValues.stream().sorted((t1, t2) -> {  

3.          return t1.getIndex() >= t2.getIndex() ? 1 : -1;  

4.      }).collect(Collectors.toList());  

5.      return result;  

6.  } 
```



2）在根据name、type匹配，不匹配说明当前构造函数不是我要找的

a. 在name匹配的时候，需要注意的是在反射获取属性的时候Paramenter中的name属性其实是arg0、arg1，这里使用了Spring的org.springframework.core.**LocalVariableTableParameterNameDiscoverer**这个类，**使用ASM字节码工具去修改class文件获取真实的属性name**

也就是这两句

```
1.  LocalVariableTableParameterNameDiscoverer parameterNameDiscoverer = new LocalVariableTableParameterNameDiscoverer();     

2.  String[] paramsName = parameterNameDiscoverer.getParameterNames(candidates[i]); 
```



b. 在type匹配的时候，需要注意的是要看两个类有没有子孙关系，本来用AClass.isAssignableFrom(BClass)就可以了，但是**考虑到有类的属性有可能是原始类型，那么这个方法就用不了**，**比如int.class和java.lang.Integer.class就不会匹配**

Spring对应的关联方法如下，将基本类型做了一下转换：

```
1.  static {  

2.      primitiveWrapperTypeMap.put(Boolean.class, Boolean.TYPE);  

3.      primitiveWrapperTypeMap.put(Byte.class, Byte.TYPE);  

4.      primitiveWrapperTypeMap.put(Character.class, Character.TYPE);  

5.      primitiveWrapperTypeMap.put(Double.class, Double.TYPE);  

6.      primitiveWrapperTypeMap.put(Float.class, Float.TYPE);  

7.      primitiveWrapperTypeMap.put(Integer.class, Integer.TYPE);  

8.      primitiveWrapperTypeMap.put(Long.class, Long.TYPE);  

9.      primitiveWrapperTypeMap.put(Short.class, Short.TYPE);  

10.     Map.Entry<Class<?>, Class<?>> entry;  

11.     for (Iterator localIterator = primitiveWrapperTypeMap.entrySet().iterator(); localIterator.hasNext();) {  

12.         entry = (Map.Entry) localIterator.next();  

13.         primitiveTypeToWrapperMap.put(entry.getValue(), entry.getKey());  

14.     }  

15. }  

16. public static boolean isAssignable(Class<?> lhsType, Class<?> rhsType) {  

17.     if (lhsType.isAssignableFrom(rhsType)) {  

18.         return true;  

19.     }  

20.     if (lhsType.isPrimitive()) {  

21.         Class<?> resolvedPrimitive = (Class) primitiveWrapperTypeMap.get(rhsType);  

22.         if (lhsType == resolvedPrimitive) {  

23.             return true;  

24.         }  

25.     } else {  

26.         Class<?> resolvedWrapper = (Class) primitiveTypeToWrapperMap.get(rhsType);  

27.         if ((resolvedWrapper != null) && (lhsType.isAssignableFrom(resolvedWrapper))) {  

28.             return true;  

29.         }  

30.     }  

31.     return false;  

32. } 
```



3）匹配成功或者说所有的<construct-arg>标签都没有index、name、type属性，这时候对bean的每一个属性进行尝试赋值操作，这里核心内容就是

```
// 核心在这里，如果不能将argumentValues中的值转换成parameterTypes中对应的类，则转型失败，类型不匹配  

Object convertedValue = typeConverter.convertIfNecessary(resolveValue, params[i].getType()); 
```

就是将resolveValue尝试转换成params[i].getType()的类，成功说明这个属性成功匹配，失败就是当前构造函数不是我要找的咯



#### **3、第三步**

在getBean()的时候判断下这个Bean中ConstructorArgument有没有值，如果有的话，说明有配置<construct-arg>标签，那么就调用上面的步骤尝试去匹配Bean中的构造函数，没有的话就new一个

对应代码如下：

```
1.  /*** 

2.   * 根据BeanDefinition初始化Bean 

3.   */  

4.  private Object initalBean(BeanDefinition bd) {  

5.      if(bd.hasConstructorArgumentValues()) {  

6.          ConstructorResolver constructorResolver = new ConstructorResolver(this);  

7.          return constructorResolver.autowiredConstructor(bd);  

8.      }  

9.      //...  

10. }  
```