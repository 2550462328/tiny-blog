Tomcat源码分析
2024-08-22
Tomcat 是一个开源的 Web 应用服务器。它实现了 Java Servlet 和 JavaServer Pages 等技术规范，能高效处理 HTTP 请求。具有易部署、性能稳定等特点，广泛应用于开发和部署 Java Web 应用，是 Java 生态中重要的组成部分。
01.jpg
源码解读
huizhang43

#### **1、tomcat 的启动流程**



下图是tomcat 的启动时序图

![img](http://pcc.huitogo.club/92eeecfa6b461721c5696f00dd7b7971)



由图中我们可以看到从Bootstrap类的main方法开始, tomcat会以链的方式逐级调用各个模块的init()方法进行初始化, 待各个模块都初始化后, 又会逐级调用各个模块的start()方法启动各个模块



下面通过源码的调用层级来看一下：

```
Catilna

		Bootstrap
		
				Server --- StandardServer                tomcat           
				
						Service --- StandardService
						
						Engine --- StandardEngine、EngineConfig          
						
						Container --- ContainerBase          webApps                   
						
										Connector(8080、443)  -> ProtocolHandler -> EndPoint  --- NIOEndPoint、NIO2EndPoint、APREndPoint
										
										Host  --- StandardHost、HosConfig                               
										
													Context --- StandardContext、ContextConfig                        webApp       
													
																Wrapper  ---   StandardWrapper                                 servlet         
```



主要分成两个大接口，Lifeclycle 和 LifecycleListener，Lifeclycle 进行 init 和 start 控制生命周期，变更状态的时候 触发LifecycleListener事件，执行lifecycleEvent

Lifeclycle ---> LifeclycleMBeanBase：ContainerBase（StandardEngine、StandardHost、StandardContext）、StandardServer、StandardService

LifecycleListener：EngineConfig、HosConfig、ContextConfig





#### **2、tomcat 的组件**



tomcat 的组件 和 组件之间的交互主要如下



![img](http://pcc.huitogo.club/5fc5d76298edbf10a46aa8369fac7df5)



**server**：整个servlet容器，一个tomcat对应一个server，一个server包含多个service，Server就掌管着多个Service的死活

server在tomcat中的实现类是：StandardServer

**service**：service是对外提供服务的， 一个service包含多个connector（接受请求的协议），和一个container（容器），多个connector共享一个container容器，

service在tomcat中的实现类是：StandardService

**connector**：connector主要用来接收请求，解析请求内容，封装request和response，然后将准备好的数据交给Container处理

**executor**：线程池

**container**：Container就是我们常说的容器，里面可以有多个Host,一个host表示一个虚拟主机，就是一个对应一个WebApps. 最后Container处理完请求之后会将响应内容返回给Connecter,再由Connecter返回给客户端包含engine，host，context，wrapper等组件

**engine**：Container（容器/引擎）， 用来管理多个站点，一个Service最多只能有一个Engine

engine在tomcat中的实现类是：StandardEngine

**host**：engine容器的子容器，一个host对应一个网络域名，一个host包含多个context

host在tomcat中的实现类是：StandardHost

**context**：host容器的子容器，表示一个web应用

context在tomcat中的实现类是：StandardContext

**wrapper**：tomcat中最小的容器单元，表示web应用中的servlet

wrapper在tomcat中的实现类是：StandardWrapper  







其中组件中最核心的是Connector 和 Container；Connector负责 请求和响应，Container 负责 处理请求 两者交互如下：



![img](http://pcc.huitogo.club/5dcf290e5aa65422ed2687f06ff4001c)



##### 2.1 Connector



connector架构：最底层使用的是Socket进行连接的，Request和Response是按照Http协议来封装的，所以Connector同时需要实现TCP/IP协议和Http协议

Connector中具体用事件处理器来处理请求【ProtocoHandler】，不同的ProtocoHandler代表不同的连接类型【所以一个Service中可以有多个Connector】 例如：Http11Protocol使用普通的Socket来连接的，Http11NioProtocol使用NioSocket连接。 Endpoint用于处理底层Socket的网络连接，用来实现Tcp/Ip协议。

Acceptor:用于监听和接收请求。

Handler：请求的初步处理，并且调用Processor

AsynTimeout:检查异步的Request请求是否超时 Processor用于将Endpoint接收Socket封装成Request，用来实现HTTP协议

Adapter 用于将Request交给Container 进行具体处理，即将请求适配到Servlet容器



##### 2.2 Container



![img](http://pcc.huitogo.club/729b44dc8f59d6aadf5efc9465e472ac)



Container 架构：Container就是一个Engine。Container用于封装和管理Servlet，以及具体处理Request请求





#### **3、CoyoteAdapter**



这里需要着重说一下 Connector 和 Container的细节



![img](http://pcc.huitogo.club/a8b78a1b823d55f60128420d931605a5)



1）Endpoint接收Socket连接，生成一个SocketProcessor任务提交到线程池去处理

2）SocketProcessor的run方法会调用Processor组件去解析应用层协议，Processor通过解析生成Request对象后，会调 用Adapter的service方法。



其中：

##### 3.1 **EndPoint**

提供字节流给Processor

监听通信端口，是对传输层的抽象，用来实现 TCP/IP 协议的。 对应的抽象类为AbstractEndPoint，有很多实现类，比如NioEndPoint，JIoEndPoint等。在其中有两个组件，一个 是Acceptor，另外一个是SocketProcessor。 Acceptor用于监听Socket连接请求，SocketProcessor用于处理接收到的Socket请求。



##### 3.2 **Processor**

提供Tomcat Request对象给Adapter

Processor是用于实现HTTP协议的，也就是说Processor是针对应用层协议的抽象。 Processor接受来自EndPoint的Socket，然后解析成Tomcat Request和Tomcat Response对象，最后通过Adapter 提交给容器。 对应的抽象类为AbstractProcessor，有很多实现类，比如AjpProcessor、Http11Processor等。



##### 3.3 **Adapter**

提供ServletRequest给容器

ProtocolHandler接口负责解析请求并生成 Tomcat Request 类。 需要把这个 Request 对象转换成 ServletRequest。 Tomcat 引入CoyoteAdapter，这是适配器模式的经典运用，连接器调用 CoyoteAdapter 的 sevice 方法，传入的是 Tomcat Request 对象，CoyoteAdapter 负责将 Tomcat Request 转成 ServletRequest，再调用容器的 service 方 法。



所以 CoyoteAdapter 是 Connector 请求的 处理适配器， 将 HttpRequest 转换成 ServletRequest 交由 Container 处理





#### **4、web.xml 和 web-fragment.xml**



web.xml 是 javaWeb项目的配置根文件（万恶之源）

Servlet 3.0 引入了称之为“Web 模块部署描述符片段”的 web-fragment.xml 部署描述文件，该文件必须存放在 JAR 文件的 META-INF 目录下，该部署描述文件可以包含一切可以在 web.xml 中定义的内容。JAR 包通常放在 WEB-INF/lib 目录下，除此之外，所有该模块使用的资源，包括 class 文件、配置文件等，只需要能够被容器的类加载器链加载的路径上，比如 classes 目录等。可以说这个新特性还是很实用的，不用把之前臃肿的配置全部放在web.xml文件中了，可以把一些初始化的配置全部配置到web-fragment.xml文件中，比如在分布式项目中，spring的包扫描，在一些公司中都会有相应的规范约束，就连controller和service等等都要求包名都要遵守规范，这样我们就可以提取出来一个工程，统一加载spring的配置文件，在web-fragment.xml中加载这些spring的配置文件，这样在其他开发者工作中，不用每次都要配置spring的几乎重复的配置，直接引用相应的jar包即可完成配置，这样可以大大提高效率。

最终 web.xml 和 web-fragment.xml 都会被加载到 WebXml中，多个文件会被merge，优先是 web.xml，后面的web-fragment.xml 按 order顺序加载





#### **5、GlobalNamingResources**

定义了服务器的全局JNDI资源





#### **6、MapperListener**

Container 资源变更时引发的刷新事件





#### **7、源码鉴赏**



1）服务包扫描 + 添加Servlet映射



```
HosConfig.deployDirectory()

	WebAppLoader.start()
	
		ContextConfig.configureStart()
```



2）http请求处理

```
AbstractProtocol.start()

	AbstractEndpoint.start()
	
		Poller.run()
		
			AbstractProtocol.process()
			
				AbstractProcessorLight.process()
				
					AbstractProcessorLight.service()
					
						Http11Processor.service()   --- getAdapter().service(request, response)
						
							CoyoteAdapter.service()   ---   connector.getService().getContainer().getPipeline().getFirst().invoke(request, response);
```