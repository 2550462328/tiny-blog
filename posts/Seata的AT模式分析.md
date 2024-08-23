Seata的AT模式分析
2024-08-22
Seata 的 AT 模式是一种分布式事务解决方案。它基于两阶段提交，一阶段业务数据和回滚日志记录一起提交，二阶段若全局事务成功则提交，失败则根据回滚日志自动回滚。提高了分布式系统中事务处理的效率和可靠性。
03.jpg
实践原理
huizhang43

**client 端 (TM 和 RM) 和 server端 （TC）**



1）初始化 client端 和 server端 通过服务发现（nacos、fille、zookeeper等） 发现对方地址 并建立 netty 连接 ，保持心跳连接



2）TM 端 和 RM在初始化的时候上传自身信息到TC (registerRMChannel、registerTMChannel)

![img](http://pcc.huitogo.club/4a30fe0ae2a30aca06154a956c2f5055)

![img](http://pcc.huitogo.club/67c1dfe79744a3f8def648b2adb75497)



3）client init 的时候 GlobalTransactionScanner 扫描 @GlobalTransaction 生成代理 AbstractAutoProxyCreator 添加了 GlobalTransactionalInterceptor 拦截逻辑



**核心方法 TransactionalTemplate.execute**



开始事务 -- sendRequest到 server端 保存 branch事务信息 （保存数据源信息、建立行锁）

-  client 处理业务 没有发生异常 --> 通知到server端 --> 根据xid 查找关联的branch 事务信息 --> 进行 branch Commit （删除undo_log）
-  client 处理业务 发生异常 --> 通知到server端 --> 根据xid 查找关联的branch 事务信息 --> 进行branch rollback（回滚并删除undo_log）

![img](http://pcc.huitogo.club/1ffb48d8d2be2f716975ace9bb89d957)