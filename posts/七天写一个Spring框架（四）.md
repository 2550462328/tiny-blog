七天写一个Spring框架（四）
2024-08-22
七天手写一个Spring轻量级框架之第四天
06.jpg
造轮子系列
huizhang43

本节目标的类图如下：

![img](http://pcc.huitogo.club/859ca9538a1d872a025bda82c6b6a11a)



**今天的目标是**

将指定目录下的文件（通常在spring的配置中以<context:component-scan base-package=””/>说明文件目录）被@Component（可以扩展更多，如@Service、@Controller）注释的类转换成Beandefinition并registry到BeanFactory中去

乍一看，挺简单

扫描目录下文件 --> 判断有没有@Component注释 --> 有的话生成BeanDefinition

细想的话，怎么检测class文件中有没有这个注释，以及@Component注释的类怎么转换成BeanDefinition呢？

先一步步实现吧



#### **1、获取目录下Resource**

扫描指定目录下的文件，然后返回Resource

这里涉及到一个递归使用，遍历目录使用递归应该还是容易想到的，将得到的File，实例化到FileSystemResource中去即可

新建一个PackageResourceLoader

```
1.  public Resource[] getResources(String basepackage) {  

2.      Assert.notNull(basepackage, "basepackage must not be null");  

3.      String location = ClassUtils.convertClassNameToResourcePath(basepackage);  

4.      ClassLoader cl = getClassLoader();  

5.      URL url = cl.getResource(location);  

6.      File rootDir = new File(url.getFile());  

7.      Set<File> matchingFiles = retrieveMatchingFiles(rootDir);  

8.      Resource[] result = new Resource[matchingFiles.size()];  

9.      int i = 0;  

10.     for (File file : matchingFiles) {  

11.         result[i++] = new FileSystemResource(file);  

12.     }  

13.     return result;  

14. }  


15. /** 

16.  * 获取rootDir子目录中的文件 

17.  */  

18. private Set<File> retrieveMatchingFiles(File rootDir) {  

19.     if (!rootDir.exists()) {  

20.         if (log.isDebugEnabled()) {  

21.             log.debug("Skipping [" + rootDir.getAbsolutePath() + "] because it is not found!");  

22.         }  

23.         return Collections.emptySet();  

24.     }  

25.     if (!rootDir.isDirectory()) {  

26.         if (log.isWarnEnabled()) {  

27.             log.debug("Skipping [" + rootDir.getAbsolutePath() + "] because it does not denote a directory!");  

28.         }  

29.         return Collections.emptySet();  

30.     }  

31.     if (!rootDir.canRead()) {  

32.         if (log.isWarnEnabled()) {  

33.             log.debug("Skipping [" + rootDir.getAbsolutePath()  + "] because the application is not allowed to read the directory!");  

35.         }  

36.         return Collections.emptySet();  

37.     }  

38.     Set<File> result = new LinkedHashSet<>();  

39.     doRetrieveMatchingFiles(rootDir, result);  

40.     return result;  

41. }  


42. /** 

43.  * 递归获取rootDir中的file文件 

44.  */  

45. private void doRetrieveMatchingFiles(File rootDir, Set<File> result) {  

46.     File[] fileList = rootDir.listFiles();  

47.     if (fileList == null) {  

48.         if (log.isWarnEnabled()) {  

49.             log.debug("Could not retrieve contents of direcotry [" + rootDir.getAbsolutePath() + "]");  

50.         }  

51.         return;  

52.     }  

53.     for (File content : fileList) {  

54.         if (content.isDirectory()) {  

55.             if (!content.canRead()) {  

56.                 if (log.isDebugEnabled()) {  

57.                     log.debug("Skipping subdirectory [" + content.getAbsolutePath() + "] because the application is not allowed to read the directory!");  

59.                 }  

60.             } else {  

61.                 doRetrieveMatchingFiles(content, result);  

62.             }  

63.         } else {  

64.             result.add(content);  

65.         }  

66.     }  

67. }  
```

去掉那些打印日志和判定文件的操作外代码还是很简短的。



#### **2、获取Resource中的注释信息**

在第一步中我们已经获取了目录下的所有文件，并且转换成了Resource，现在我们要尝试读取Resource并获得注释信息，需要注意的是这里的Resource是Java文件编译后的class文件，所以我们需要借助ASM字节码工具。

首先介绍一下ASM的工作机制

1）新建一个ClassReader去读取指定class文件

2）新建一个ClassVisitor去接收ClassReader读取的值

这里接收的值 有visit --> visit annotation --> visit filed --> visit method --> visit end这些过程

3）ClassVisiot接收到值后可以借助ClassWriter再将修改后的值写入class文件



需要注意的是，这里ClassVisitor需要自定义，也就是自己实现ClassVisitor接口

我们先尝试去实现简单的读取类信息

先定义一个ClassMetadataReadingVistor去接收读取到的类信息

```
1.  @Data  

2.  public class ClassMetadataReadingVistor extends ClassVisitor implements ClassMetadata {  

3.      private String className;  

4.      private boolean isInterface;  

5.      private boolean isAbstract;  

6.      private boolean isFinal;  

7.      private String superClassName;  

8.      private String[] interfaces;  

9.      public ClassMetadataReadingVistor() {  

10.         super(SpringAsmInfo.ASM_VERSION);  

11.     }  


12.     /** 

13.      * 这里只覆盖了一个方法获取class文件的类信息 

14.      */  

15.     @Override  

16.     public void visit(int version, int access, String name, String signature, String superName, String[] interfaces) {  

17.         this.className = ClassUtils.convertResourcePathToClassName(name);  

18.         this.isInterface = (access & Opcodes.ACC_INTERFACE) != 0;  

19.         this.isAbstract = (access & Opcodes.ACC_ABSTRACT) != 0;  

20.         this.isFinal = (access & Opcodes.ACC_FINAL) != 0;  

21.         if(StringUtils.isNotBlank(superName)) {  

22.             this.superClassName = ClassUtils.convertResourcePathToClassName(superName);  

23.         }  

24.         this.interfaces = new String[interfaces.length];  

25.         System.arraycopy(interfaces, 0, this.interfaces, 0, interfaces.length);  

26.         this.interfaces = Stream.of(this.interfaces).map(str -> ClassUtils.convertResourcePathToClassName(str)).toArray(String[]::new);  

27.     }     

28. }     
```



ClassVisitor跟ClassReader交互的过程非常简单，类似这种

```
1.  ClassPathResource resource = new ClassPathResource( "my_spring/beanfactory_annotation/test/service/PersonService.class");  

3.  ClassReader reader = new ClassReader(resource.getInputStream());  

4.  ClassMetadataReadingVistor visitor = new ClassMetadataReadingVistor();  

5.  reader.accept(visitor, ClassReader.SKIP_DEBUG);  
```

这个过程就感觉像是两个人在打电话，一个人（Visitor）希望另一个人(Reader)帮它查点东西，这里就是resource的信息，accept方法表示 电话通了，开始沟通



现在我们开始去读取注释信息

因为注释信息里面有很多属性，比如@Component(value=”personService”)中的value = personService

先新建一个AnnotationAttribute去装这些属性

```
1.  public class AnnotationAttribute extends LinkedHashMap<String, Object> {  

2.      public AnnotationAttribute(int initialCapacity) {  

3.          super(initialCapacity);  

4.      }  

5.      public String getString(String attributeName) {  

6.          return doGet(attributeName, String.class);  

7.      }  


8.      private <T> T doGet(String attribteName, Class<T> expectedType){  

9.          Object value = get(attribteName);  

10.         if (!expectedType.isInstance(value) && expectedType.isArray() && expectedType.getComponentType().isInstance(value)) {  

12.             Object array = Array.newInstance(expectedType.getComponentType(), 1);  

13.             Array.set(array, 0, value);  

14.             value = array;  

15.         }  

16.         return (T)value;  

17.     }  

18. }  
```

其实就是一个LinkedHashMap，只是多了一个将map中的value转换成任意类型的能力，也就是doGet方法



现在可以新建一个AnnotationMetadataReadingVisitor来接收ClassReader传递的注释信息

```
1.  @Data  

2.  public class AnnotationMetadataReadingVisitor extends ClassMetadataReadingVistor{  

3.      private final Set<String> annotationTypes = new LinkedHashSet<>();  

4.      private final Map<String, AnnotationAttribute> attributeMap = new LinkedHashMap<>(4);  

5.      @Override  

6.      public AnnotationVisitor visitAnnotation(final String desc, boolean visible) {  

7.          String annotationName = Type.getType(desc).getClassName();  

8.          this.annotationTypes.add(annotationName);  

9.          // 这里ClassReader已经将类的注释类传过来了，然后我告诉它，如果这个类有详情的话打我下面这个电话  

10.         return new AnnotationAttributesReadingVisitor(annotationName, this.attributeMap);  

11.     }  

12.     public AnnotationAttribute getAnnotationAttribute(String annotation) {  

13.         return attributeMap.get(annotation);  

14.     }  

15.     public boolean hasAnnotation(String annotation) {  

16.         return this.annotationTypes.contains(annotation);  

17.     }  

18. }
```

这里AnnotationMetadataReadingVisitor是ClassMetadataReadingVistor的子类



注意这里visitAnnotation接收的只是注释的大概信息，如果想知道详细信息的话还得给ClassReader留一个“电话”（AnnotationVisitor）

这里新建AnnotationAttributesReadingVisitor去接收指定注释的详细信息

```
1.  public class AnnotationAttributesReadingVisitor extends AnnotationVisitor {  

2.      private final String annotationType;  

3.      private final Map<String, AnnotationAttribute> attributeMap;  

4.      AnnotationAttribute attribute = new AnnotationAttribute();  

5.      public AnnotationAttributesReadingVisitor(String annotationType, Map<String, AnnotationAttribute> attributeMap) {  

7.          super(SpringAsmInfo.ASM_VERSION);  

8.          this.annotationType = annotationType;  

9.          this.attributeMap = attributeMap;  

10.     }  

11.     @Override  

12.     public void visit(String name, Object value) {  

13.         this.attribute.put(name, value);  

14.     }  

15.     @Override  

16.     public void visitEnd() {  

17.         this.attributeMap.put(this.annotationType, this.attribute);  

18.     }  

19. }
```

现在我们就完成了从Resource中读取注释信息的目的了



#### **3、包装一下Reader和Visitor的交互过程**

虽然我们已经完成了从Resource中读取注释信息，但是我们使用这些东西的时候是非常繁琐的，而且会将ASM操作的方法暴露出来，很明显这不符合解耦隔离的设计理念

再看一下如何从Resource中读取注释信息

```
1.  ClassPathResource resource = new ClassPathResource( "my_spring/beanfactory_annotation/test/service/PersonService.class");  

3.  ClassReader reader = new ClassReader(resource.getInputStream());  

4.  AnnotationMetadataReadingVisitor visitor = new AnnotationMetadataReadingVisitor();  

5.  reader.accept(visitor, ClassReader.SKIP_DEBUG);  

6.  String annotation = "my_spring.beanfactory_annotation.stereotype.Component";  

7.  AnnotationAttribute attribute = visitor.getAnnotationAttribute(annotation);  
```



其实上面的内容我们操作的地方就是传入一个Resouce地址，然后获取到一个Visitor

这里进行包装一下，使用包装类解析Resource，返回Visitor

秉着面向接口开发而不是面向实现的原则，新建MetadataReader接口

```
1.  public interface MetadataReader {  

2.      Resource getResource();  

3.      ClassMetadata getClassMetadata();  

4.      AnnotationMetadata getAnnotationMetadata();  

5.  }  
```



新建一个MetadataReader接口的默认实现类SimpleMetadaReader

```
1.  @Data  

2.  public class SimpleMetadaReader implements MetadataReader {  

3.      private final Resource resource;  

4.      private final ClassMetadata classMetadata;  

5.      private final AnnotationMetadata annotationMetadata;  

6.      public SimpleMetadaReader(Resource resource) throws IOException {  

7.          ClassReader reader;  

8.          try (InputStream is = new BufferedInputStream(resource.getInputStream())) {  

9.              reader = new ClassReader(is);  

10.         }  

11.         AnnotationMetadataReadingVisitor visitor = new AnnotationMetadataReadingVisitor();  

12.         reader.accept(visitor, ClassReader.SKIP_DEBUG);  

13.         this.classMetadata = visitor;  

14.         this.annotationMetadata = visitor;  

15.         this.resource = resource;  

16.     }  

17. }  
```

可以看到熟悉的代码，没错，就是把visitor跟reader交互的过程在这里做了。



现在利用这个包装类我们读取Resource的步骤如下

```
1.  ClassPathResource resource = new ClassPathResource("my_spring/beanfactory_annotation/test/service/PersonService.class");  

3.  MetadataReader reader = new SimpleMetadaReader(resource);  

4.  AnnotationMetadata amd = reader.getAnnotationMetadata();  

5.  String annotation = Component.class.getName();  

6.  AnnotationAttribute attribute = amd.getAnnotationAttribute(annotation);  
```

隐藏了ASM的实现细节，一个简单的包装类就完成了。



#### **4、主要流程**

现在我们已经具备筛选具备@Component注释的Resource的能力了，下一步就是将这些Resource转换成BeanDefinition，并且转到BeanFactory中

首先Resource转换过来的BeanDefinition用GenericBeanDefinition来装肯定是不合适的，所以我们新建了一个ScannedGenericBeanDefinition 

ScannedGenericBeanDefinition 和BeanDefinition关系如下图：

![img](http://pcc.huitogo.club/943a3b46cd1edf1457ca108e96f7fb34)



ScannedGenericBeanDefinition 代码如下：

```
1.  // 新建一个接口赋予新的BeanDefinition新能力  

2.  public interface AnnotatedBeanDefinition extends BeanDefinition {  

3.      AnnotationMetadata getMetadata();  

4.  }  

5.  public class ScannedGenericBeanDefinition extends GenericBeanDefinition implements AnnotatedBeanDefinition{  

6.      private final AnnotationMetadata metadata;  

7.      public ScannedGenericBeanDefinition(AnnotationMetadata metadata) {  

8.          super();  

9.          this.metadata = metadata;  

10.         setClassName(metadata.getClassName());  

11.     }  

12.     @Override  

13.     public AnnotationMetadata getMetadata() {  

14.         return metadata;  

15.     }  

16. } 
```



现在我们新建一个类ClassPathBeanDefinitionScanner负责扫描指定目录进行筛选和装载的操作

```
1.  public class ClassPathBeanDefinitionScanner {  

2.      private final BeanDefinitionRegistry registry;  

3.      private PackageResourceLoader resourceLoader = new PackageResourceLoader();  

4.      private BeanNameGenerator beanNameGenerator = new AnnotationBeanNameGenerator();  

5.      protected final Logger logger = LoggerFactory.getLogger(getClass());  

6.      public ClassPathBeanDefinitionScanner(BeanDefinitionRegistry registry) {  

7.          this.registry = registry;  

8.      }  


9.      /** 

10.      * 扫描指定的数组包，生成BeaDefinition集合，并注册到BeanFactory中 

11.      * @param packagesToScan 

12.      * @return 

13.      * @throws IOException 

14.      */  

15.     public Set<BeanDefinition> doScan(String packagesToScan) throws IOException {  

16.         String[] basePackages = StringUtils.split(packagesToScan, ",");  

17.         Set<BeanDefinition> beanDefinitions = new LinkedHashSet<>();  

18.         for (String basePackage : basePackages) {  

19.             Set<BeanDefinition> candidates = findCandidateComponents(basePackage);  

20.             for(BeanDefinition candidate :candidates) {  

21.                 beanDefinitions.add(candidate);  

22.                 registry.registryBeanDefinition(candidate.getId(), candidate);  

23.             }  

24.         }  

25.         return beanDefinitions;  

26.     }  


27.     private Set<BeanDefinition> findCandidateComponents(String basePackage) throws IOException {  

28.         Set<BeanDefinition> candidates = new LinkedHashSet<>();  

29.         Resource[] resources = resourceLoader.getResources(basePackage);  

30.         MetadataReader reader = null;  

31.         AnnotationMetadata metadata = null;  

32.         ScannedGenericBeanDefinition beanDefinition = null;  

33.         String componentName = Component.class.getName();  

34.         for (Resource resource : resources) {  

35.             reader = new SimpleMetadaReader(resource);  

36.             metadata = reader.getAnnotationMetadata();  

37.             if (metadata.hasAnnotation(componentName)) {  

38.                 beanDefinition = new ScannedGenericBeanDefinition(metadata);  

39.                 // 根据BeanDefinition生成对应的beanName  

40.                 String beanId = beanNameGenerator.generateBeanName(beanDefinition, registry);  

41.                 beanDefinition.setId(beanId);  

42.                 candidates.add(beanDefinition);  

43.             }  

44.         }  

45.         return candidates;  

46.     }  

47. }  
```



过程还是很简单的，通过步骤3中的包装类解析Resource获得AnnotationMetadata，然后传给ScannedGenericBeanDefinition 就可以了

这里有一点要注意的就是ScannedGenericBeanDefinition 的beanId怎么确认？

1）如果@Component的value属性有值就用这个值

2）如果没有就拿className，需要将className首字母小写



这部分Spring代码个人觉得太繁琐了就不展示了

其实就是从AnnotationMetadata中获取到@Component对应的value属性，判断一下，没有值就对className处理一下就当作beanId了。

使用ClassPathBeanDefinitionScanner扫描目录并装载BeanDefinition的代码如下：

```
1.  DefaultBeanFactory factory = new DefaultBeanFactory();  

2.  String basePackage = "my_spring.beanfactory_annotation";  

3.  ClassPathBeanDefinitionScanner scanner = new ClassPathBeanDefinitionScanner(factory);  

4.  scanner.doScan(basePackage);  

5.  BeanDefinition bd = factory.getBeanDefinition("personService");  

6.  //...  
```



#### **5、在xml加载的时候进行扫描装载**

这个过程比较简单了，我们顺便重构一下之前的XmlBeanDefinitionReader.loadBeanDefinition这部分代码

之前我们只考虑从xml中获取Bean并装载，现在多了个扫描目录文件 + 装载

重构后的代码如下：

```
1.  public void loadBeanDefinition(Resource resource) {  

2.      InputStream is = null;  

3.      try {  

4.          is = resource.getInputStream();  

5.          SAXReader reader = new SAXReader();  

6.          Document doc = reader.read(is);  

7.          Element root = doc.getRootElement();  

8.          Iterator<Element> itr = root.elements().iterator();  

9.          while (itr.hasNext()) {  

10.             Element ele = itr.next();  

11.             String namespaceUri = ele.getNamespaceURI();  

12.             // 判断标签的命名空间  

13.             if (isDefaultNamespace(namespaceUri)) {  

14.                 parseDefaultElement(ele);  

15.             } else if (isContextNamespace(namespaceUri)) {  

16.                 parseComponentElement(ele);  

17.             }  

18.         }  

19.     } catch (DocumentException | IOException e) {  

20.         throw new BeanStoreException("configFile is valid xml file!");  

21.     } finally {  

22.         if (is != null) {  

23.             try {  

24.                 is.close();  

25.             } catch (IOException e) {  

26.                 e.printStackTrace();  

27.             }  

28.         }  

29.     }  

30. }  


31.  /** 

32.  * 解析Bean类型的标签 

33.  */  

34. private void parseDefaultElement(Element ele) {  

35.     String id = ele.attributeValue(ID_ATTRIBUTE);  

36.     String beanClassName = ele.attributeValue(CLASS_ATTRIBUTE);  

37.     BeanDefinition bd = new GenericBeanDefinition(id, beanClassName);  

38.     if (ele.attribute(SCOPE_ATTRIBUTE) != null) { // 判断bean的scope  

39.         bd.setScope(ele.attributeValue(SCOPE_ATTRIBUTE));  

40.     }  

41.     // 解析bean中construct-arg标签，放入到BeanDefinition中的constructorArguments中  

42.     this.parseConstructorArgElements(ele, bd);  

43.     // 解析bean的property标签，放入到BeanDefinition中的propertyValue中  

44.     this.parsePropertyElement(ele, bd);  

45.     // 向BeanFactory注册BeanDefinition  

46.     this.registry.registryBeanDefinition(id, bd); // 这里用BeanDefinitionRegistry 替代了container  

47. }  


48. /** 

49.  * 解析context类型的标签 

50.  */  

51. private void parseComponentElement(Element ele) throws IOException {  

52.     String basePackage = ele.attributeValue(BASE_PACKAGE_ATTRIBUTE);  

53.     ClassPathBeanDefinitionScanner scanner = new ClassPathBeanDefinitionScanner(registry);  

54.     scanner.doScan(basePackage);  

55. }  


56. /** 

57.  * 判断命名方式是不是bean(default) 

58.  */  

59. private boolean isDefaultNamespace(String namespaceUri) {  

60.     return (!StringUtils.hasLength(namespaceUri) || BEANS_NAMESPACE_URI.equals(namespaceUri));  

61. }  


62. /** 

63.  * 判断命名方式是不是context 

64.  */  

65. private boolean isContextNamespace(String namespaceUri) {  

66.     return (!StringUtils.hasLength(namespaceUri) || CONTEXT_NAMESPACE_URI.equals(namespaceUri));  

67. }  
```

这里就是多了一步判断，看看你是不是使用的context下的标签，也就是<context:component-scan>，如果是的就用ClassPathBeanDefinitionScanner去扫描装载，不然就用之前的方法就可以了。



#### **6、总结**

1）如何使用ASM去操作class文件，获取想要的信息。

2）面向接口编程，而不是面向实现编程，凡事多用接口，比如这里对于MetaDataVisitor，都先新建对应的接口MetaData，以及在扩展BeanDefiniton的时候先使用一个接口AnnotatedBeanDefinition来表示新能力。

3）面向修改关闭，面向扩展开放，比如这里面需要扩展BeanDefiniton的时候，使用一个接口AnnotatedBeanDefinition来表示新能力，并且还让这个新扩展出来的BeanDefinition去继承老的BeanDefinition。