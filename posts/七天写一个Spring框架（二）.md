七天写一个Spring框架（二）
2024-08-22
七天手写一个Spring轻量级框架之第二天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/abb372169aca567b8cc5ae10e101e53c)



今天的目标是

获取bean的属性值和引用对象，在xml中如下所示

```
1.  <bean id = "personService" class="my_spring.beanfactory_set.test.service.PersonService">  

2.      <property name="eatDao" ref="eatDao" />  

3.      <property name="drinkDao" ref="drinkDao" />  

4.      <property name="name" value="zhanghui" />  

5.      <property name="age" value="18" />  

6.  </bean>  
```



编写出来的成功测试用例如下

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

带着这个目的出发开始思考怎么设计了

对于<property>标签，我们使用PropertyValue来表示

在解析xml的时候，将每个<bean>标签下的<property>标签解析成PropertyValue，放入到对应BeanDefinition中的List<PropertyValue>中

在getBean()的时候，需要根据BeanDefinition里的List<PropertyValue>给bean设置属性值



在PropertyValue中

对于name-value的property存储的是propertyName - value（常量）

对于name-ref的property存储的是propertyName - ref （BeanName）

所以**对于name-ref的property在设置属性之前还需要解析出真正的bean实例**



对于细节问题，后面进行的时候再考虑

先构建**PropertyValue**来存储bean中property的键值，并且在BeanDefinition中加入List<PropertyValue>相关方法

PropertyValue代码如下

```
1.  @Data  

2.  public class PropertyValue {  

3.      private final String name;  

4.      private final Object value;  

5.      private boolean converted = false; // 对于name-ref的情形是否已转换        

6.      private  String convertedValue; // name-ref情形转换后的值  

7.      public PropertyValue(String name, Object value) {  

8.          super();  

9.          this.name = name;  

10.         this.value = value;  

11.     }  

12. } 
```



这个时候考虑到name-value和name-ref的情况，所以对PropertyValue的value值创建不同的实例来表示

name-value的情况用**TypedStringValue**表示PropertyValue的value

```
1.  @Data  

2.  public class TypedStringValue {  

3.      private final String value;  

4.  }
```



name-ref的情况用**RuntimeBeanReference**表示PropertyValue的value

```
1.  @Data  

2.  public class RuntimeBeanReference {  

3.      private final String name;  

4.  }  
```



解析xml中<bean>标签下的<property>标签成PropertyValue并放到对应BeanDefinition的List<PropertyValue>中

```
1.  public void loadBeanDefinition(Resource resource) {  

2.       //...  

3.      // 解析bean的property放到propertyValue中  

4.      this.parsePropertyElement(ele, bd);  

5.        this.registry.registryBeanDefinition(id, bd);   

6.  }  


7.  /** 

8.   * 解析ele下的所有property标签，并放入BeanDefinition中PropertyValue的集合中 

9.   */  

10. public void parsePropertyElement(Element ele, BeanDefinition bd) {  

11.     Iterator itr = ele.elementIterator(PROPERTY_ELEMENT);  

12.     while (itr.hasNext()) {  

13.         Element propElement = (Element) itr.next();  

14.         String propertyName = propElement.attributeValue(NAME_ATTRIBUTE);  

15.         if (!StringUtils.hasLength(propertyName)) {  

16.             return;  

17.         }  

18. //这里value可以是TypedStringValue也可能是RuntimeBeanReference

19.         Object value = this.parsePropertyValue(propElement, bd, propertyName);  

20.         bd.getPropertyValues().add(new PropertyValue(propertyName, value));  

21.     }  

22. }  


23. /** 

24.  * 根据property标签的name去解析这个property的value，这个value可以是ref，也可以是value 

25.  */  

26. public Object parsePropertyValue(Element ele, BeanDefinition bd, String propertyName) {  

27.     String elementName = (propertyName != null) ? "<property> element for property '" + propertyName + "'" : "<construct-arg> element";  

28.     boolean hasRefAttribute = (ele.attribute(REF_ATTRIBUTE) != null);  

29.     boolean hasValueAttribute = (ele.attribute(VALUE_ATTRIBUTE) != null);  

30.     if (hasRefAttribute) {  

31.         String refName = ele.attributeValue(REF_ATTRIBUTE);  

32.         if (!StringUtils.hasText(refName)) {  

33.             System.err.println(elementName + "contains empty 'ref' attribute");  

34.         }  

35.         RuntimeBeanReference ref = new RuntimeBeanReference(refName);  

36.         return ref;  

37.     } else if (hasValueAttribute) {  

38.         TypedStringValue valueHolder = new TypedStringValue(ele.attributeValue(VALUE_ATTRIBUTE));  

39.         return valueHolder;  

40.     } else {  

41.         throw new RuntimeException(elementName + "must specify a ref or value");  

42.     }  

43. }  
```



在getBean()中对bean设置属性之前有两个问题

1）对于property是name-ref的话，我们应该给bean设置的是ref的实例bean，这就涉及一个获取实例bean的问题

2）对于property是name-value的话，如果value是int类型，我们给bean做setValue是报错的，如果value是string类型就不会报错，这就涉及一个将int转换成string的问题



对于问题一

使用一个接口**BeanDefinitionValueResolver**去实现转换实例bean

```
1.  /** 

2.   * 将beanId解析成实例Bean 

3.   */  

4.  public class BeanDefinitionValueResolver {  

5.      private final DefaultBeanFactory defaultBeanFactory;  

6.      public BeanDefinitionValueResolver(DefaultBeanFactory defaultBeanFactory) {  

7.          super();  

8.          this.defaultBeanFactory = defaultBeanFactory;  

9.      }  


10. //这里解析PropertyValue中TypedStringValue 和 RuntimeBeanReference 

11.     public Object resolveValueIfNecessary(Object value) {  

12.         if (value instanceof RuntimeBeanReference) {  

13.             RuntimeBeanReference ref = (RuntimeBeanReference) value;  

14.             String refName = ref.getName();  

15.             Object bean = this.defaultBeanFactory.getBean(refName);  

16.             return bean;  

17.         } else if (value instanceof TypedStringValue) {  

18.             TypedStringValue stringValue = (TypedStringValue) value;  

19.             return stringValue.getValue();  

20.         } else {  

21.             throw new RuntimeException("the value " + value + " has not implemented");  

22.         }  

23.     }  

24. }  
```



对于问题二，也需要做一下类型转换

定义接口**TypeConverter**如下

```
1.  public interface TypeConverter {  

2.      public abstract <T> T convertIfNecessary(Object value, Class<T> requiredType) throws TypeMismatchException;  

3.  } 
```



TypeConverter接口的默认实现类**SimpleTypeConverter**

这里涉及到的如何将String转换成number以及String转换成boolean因为比较复杂，用的就是spring源码的

```
1.  public class SimpleTypeConverter implements TypeConverter {  

2.      private Map<Class<?>, PropertyEditor> defaultEditors;  

3.      @Override  

4.      public <T> T convertIfNecessary(Object value, Class<T> requiredType) throws TypeMismatchException{  

5.  // 判断value的类型是不是requiredType类或者子类  

6.          if(ClassUtils.isAssignableValue(requiredType, value)) { 

7.              return (T)value;  

8.          }else {  

9.              if(value instanceof String) {   

10. // 这个就是用来转换的工具类，核心就是PropertyEditor 

11.                 PropertyEditor editor = findDefaultEditor(requiredType); 

12.                 try {  

13.                     editor.setAsText((String)value);    

14.                 } catch (IllegalArgumentException e) {  

15.                     throw new TypeMismatchException("illegal argument " + value);  

16.                 }  

17.                 return (T)editor.getValue();  

18.             }else {  

19.                 throw new RuntimeException("can`t convert value for " + value + " class:" + requiredType);  

20.             }  

21.         }  

22.     }  


23.     private PropertyEditor findDefaultEditor(Class<?> requiredType) {  

24.         PropertyEditor editor = this.getDefaultEditor(requiredType);  

25.         if(editor == null) {  

26.             throw new RuntimeException("Editor for " + requiredType + "has not been implemented!");  

27.         }  

28.         return editor;  

29.     }  


30.     private PropertyEditor getDefaultEditor(Class<?> requiredType) {  

31.         if(this.defaultEditors == null) {  

32.             createDefaultEditors();  

33.         }  

34.         return this.defaultEditors.get(requiredType);  

35.     }  


36.     private void createDefaultEditors() {  

37.         this.defaultEditors = new HashMap<>(64);  

38.  // 转换成boolean  

39.         this.defaultEditors.put(boolean.class, new CustomBooleanEditor(false));

40.         this.defaultEditors.put(Boolean.class, new CustomBooleanEditor(true));  

41.         // 转换成int 

42.         this.defaultEditors.put(int.class, new CustomNumberEditor(Integer.class, false));  

43.         this.defaultEditors.put(Integer.class, new CustomNumberEditor(Integer.class, true);

44.         //TODO（其他类型的Editor都可以在这里加入）  

45.     }  

46. }  
```



有了解析类和转换类之后，在getBean()时的代码修改如下：

```
1.  @Override  

2.  public Object getBean(String beanId) {  

3.      BeanDefinition bd = this.getBeanDefinition(beanId);  

4.      if (bd == null) {  

5.          return null;  

6.      }  

7.  // 放入单例和获取单例

8.      if (bd.isSingleton()) {   

9.          Object bean = this.getSingleton(beanId);  

10.         if (bean == null) {  

11.             bean = createBean(bd);  

12.             this.registrySingleton(beanId, bean);  

13.         }  

14.         return bean;  

15.     }  

16. // 初始化bean

17.     return createBean(bd);  

18. }  


19. /** 

20.  * 创造bean，并给bean的property赋值 

21.  */  

22. public Object createBean(BeanDefinition bd) {  

23.     Object bean = initalBean(bd);  

24.     // 给bean设置属性  

25.     populateBean(bd, bean);  

26.     return bean;  

27. }  


28. /**

29.  * 根据BeanDefinition初始化Bean 

30.  */  

31. public Object initalBean(BeanDefinition bd) {  

32.     String className = bd.getClassName();  

33.     ClassLoader cl = this.getClassLoader();  

34.     try {  

35.         Class<?> clazz = cl.loadClass(className);  

36.         return clazz.newInstance();  

37.     } catch (Exception e) {  

38.         throw new BeanCreateException("create bean " + className + "failed!");  

39.     }  

40. }  


41. /** 

42.  * 给bean设置属性 

43.  */  

44. protected void populateBean(BeanDefinition bd, Object bean) {  

45.     List<PropertyValue> pvList = bd.getPropertyValues();  

46.     if (pvList.isEmpty()) {  

47.         return;  

48.     }  

49.     BeanDefinitionValueResolver resolver = new BeanDefinitionValueResolver(this);  

50.     SimpleTypeConverter typeConverter = new SimpleTypeConverter();  

51.     for (PropertyValue pv : pvList) {  

52.         String propertyName = pv.getName();  

53.         Object orignalValue = pv.getValue();  

54. //获取转换之后的数据

55.         Object resolvedValue = resolver.resolveValueIfNecessary(orignalValue);  

56.         try {  

57.             // 反射设置属性  

58.             BeanInfo beanInfo = Introspector.getBeanInfo(bean.getClass());  

59.             PropertyDescriptor[] pds = beanInfo.getPropertyDescriptors();  

60.             for (PropertyDescriptor pd : pds) {  

61.                 if (propertyName.equals(pd.getName())) {  

62.                     // 类型不匹配时进行转换，主要是将string类型转换成其他类  

63.                     Object convertedValue = typeConverter.convertIfNecessary(resolvedValue, pd.getPropertyType());  

64.                     pd.getWriteMethod().invoke(bean, convertedValue);  

65.                 }  

66.             }  

67.         } catch (Exception e) {  

68.             log.error(e.getMessage(),e);  

69.         } 

70.     }  

71. }  
```



上述写法是Spring里面源码的写法，其实对于将String转换成Number和给bean设置属性值有个封装好的工具类org.apache.commons.beanutils.BeanUtils.setProperty()

```
1.  for (PropertyValue pv : pvList) {  

2.      String propertyName = pv.getName();  

3.      Object orignalValue = pv.getValue();  

4.      Object resolvedValue = resolver.resolveValueIfNecessary(orignalValue);  

5.      // 本节的String转换成Number和给bean设置属性的过程可以直接用这个代替  

6.      try {  

7.          BeanUtils.setProperty(bean, propertyName, resolvedValue);  

8.      } catch (IllegalAccessException e) {  

9.          log.error(e.getMessage());  

10.     } catch (InvocationTargetException e) {  

11.         log.error(e.getMessage());  

12.     } 

13. }
```