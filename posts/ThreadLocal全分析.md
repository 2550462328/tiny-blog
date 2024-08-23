ThreadLocal全分析
2024-08-22
ThreadLocal 为每个使用它的线程提供独立的变量副本。它能实现线程间数据隔离，避免多线程对共享变量的并发访问问题。不同线程可独立操作自己的变量，互不干扰，常用于存储线程局部的状态信息，如用户会话数据等。
02.jpg
Java基础
huizhang43

#### **1、ThreadLocal的用处**

当使用ThreadLocal维护变量时，ThreadLocal为每个使用该变量的线程提供独立的变量副本，所以每一个线程都可以独立地改变自己的副本，而不会影响其它线程所对应的副本。

**ThreadLocal的作用是提供线程内的局部变量，这种变量在线程的生命周期内起作用，减少同一个线程内多个函数或者组件之间一些公共变量的传递的复杂度。**

从线程的角度看，目标变量就像是线程的本地变量，这也是类名中“Local”所要表达的意思。



#### **2、ThreadLocal的使用**

基本使用如下：

```
1.  private ThreadLocal<String> threadLocal = new ThreadLocal<>();  

2.   public static void main(String[] args) {  

3.      CyclicBarrier cyclicBarrier = new CyclicBarrier(10);  

4.      for (int i = 0; i < 10; i++) {  

5.          TestThread testThread = new ThreadLocalTest().new TestThread(cyclicBarrier);  

6.          testThread.start();  

7.          // 等待线程执行完毕  

8.          testThread.yield();  

9.      }  

10. }  


11. class TestThread extends Thread {  

12.     private CyclicBarrier cyclicBarrier;  

13.     public TestThread(CyclicBarrier cyclicBarrier) {  

14.         this.cyclicBarrier = cyclicBarrier;  

15.     }  

16.     @Override  

17.     public void run() {  

18.         try {  

19.             // 保证10个线程同时启动  

20.             cyclicBarrier.await();  

21.             threadLocal.set(Thread.currentThread().getName());  

22.             System.out.println(Thread.currentThread().getName() + ": " +  threadLocal.get());  

23.         } catch (Exception e) {  

24.             e.printStackTrace();  

25.         }   

26.     }  

27. }  
```



#### **3、一个简单的ThreadLocal**

一个简单的ThreadLocal可以只包含set、get、initValue、clear四个方法。

```
1.  public class SimpleThreadLocal<T> {  

2.      private Map<Thread, T> localMaps = Collections.synchronizedMap(new HashMap<>());  

3.      protected T initValue() {  

4.          return null;  

5.      }  

6.      public void set(T t) {  

7.          localMaps.put(Thread.currentThread(), t);  

8.      }  

9.      public T get() {  

10.         Thread thread = Thread.currentThread();  

11.         T t = localMaps.get(thread);  

12.         if (t == null && !localMaps.containsKey(thread)) {  

13.             t = initValue();  

14.             localMaps.put(thread, t);  

15.         }  

16.         return t;  

17.     }  

18.     public void clear() {  

19.         localMaps.remove(Thread.currentThread());  

20.     }  

21. }  
```



#### **4、ThreadLocal源码的实现**

##### （1）set方法

源码如下

```
1.  public void set(T value) {  

2.      Thread t = Thread.currentThread();  

3.      ThreadLocalMap map = getMap(t);  

4.      if (map != null)  

5.          map.set(this, value);  

6.      else  

7.          createMap(t, value);  

8.  }  
```



##### （2）getMap()代码

```
1.  ThreadLocalMap getMap(Thread t) {  

2.      return t.threadLocals;  

3.  }  
```



t.threadLocals是什么呢？

```
1.  class Thread implements Runnable {  

2.      //...  

3.      ThreadLocal.ThreadLocalMap threadLocals = null;  

4.      //...  

5.  }  
```

可以看到threadLocals是Thread里面的一个变量，它的类型是ThreadLocal.ThreadLocalMap，这个ThreadLocalMap下面再说，可以看到这里threadLocals赋值null

那在哪里初始化的？



还是回到set()方法，在map == null的时候，createMap(t, value)方法对threadLocals进行初始化

createMap代码如下

```
1.  void createMap(Thread t, T firstValue) {  

2.      t.threadLocals = new ThreadLocalMap(this, firstValue);  

3.  }  
```



现在set()方法的流程就很清晰了

1） 寻找当前线程的threadLocals，有的话直接put值，没有的话新建一个

2）put值的时候，是将当前的ThreadLocal作为ThreadLocalMap的key，set方法的参数value作为ThreadLocalMap的value。

看到这儿其实已经知道ThreadLocal怎么实现线程安全的了，对每一个线程都维护一个threadLocals变量，然后将当前的（threadLocal，value）插入threadLocals中。



ThreadLocal和Thread的关系如下图：

![img](http://pcc.huitogo.club/b66dd36bddad099dd26ba8f933c31306)



##### （3）get方法

get方法源码如下

```
1.  public T get() {  

2.      Thread t = Thread.currentThread();  

3.      ThreadLocalMap map = getMap(t);  

4.      if (map != null) {  

5.          ThreadLocalMap.Entry e = map.getEntry(this);  

6.          if (e != null) {  

7.              @SuppressWarnings("unchecked")  

8.              T result = (T)e.value;  

9.              return result;  

10.         }  

11.     }  

12.     return setInitialValue();  

13. }  
```



可以看到获取到了当前线程的threadLocals里面key为this.threadLocal的value值，如果当前线程threadLocals == null的话，初始化操作如下：

```
1.  private T setInitialValue() {  

2.      T value = initialValue();  

3.      Thread t = Thread.currentThread();  

4.      ThreadLocalMap map = getMap(t);  

5.      if (map != null)  

6.          map.set(this, value);  

7.      else  

8.          createMap(t, value);  

9.      return value;  

10. }  
```

主要也就set/get方法了。



#### **5、ThreadLocalMap是什么？**

ThreadLocalMap从字面上就可以看出这是一个保存ThreadLocal对象的map(其实是以它为Key)

（1）Entry

跟所有Map集合一样，ThreadLocalMap维护的也是一个Entry数组，初始化大小为16

但是ThreadLocalMap的Entry其实是包装后的ThreadLocal



Entry代码如下：

```
1.  static class Entry extends WeakReference<ThreadLocal<?>> {  

2.      Object value;  

3.     // 这里可以看到Entry的key是一个弱引用

4.      Entry(ThreadLocal<?> k, Object v) {  

5.          super(k);  

6.          value = v;  

7.      }  

8.  }  
```

可以看到它就是个扩展了弱引用类型的ThreadLocal对象，并且它里面的“key”就是个弱引用的ThreadLocal。



（2）构造函数

ThreadLocal的一个构造函数如下：

```
1.  ThreadLocalMap(ThreadLocal<?> firstKey, Object firstValue) {  

2.      table = new Entry[INITIAL_CAPACITY];  

3.      int i = firstKey.threadLocalHashCode & (INITIAL_CAPACITY - 1);

4.      table[i] = new Entry(firstKey, firstValue);  

5.      size = 1; 

6.  // 设置扩容阀值 

7.      setThreshold(INITIAL_CAPACITY);  

8.  }  
```

可以看到它内部维护的Entry数组，并且初始化大小为16，在size > (2/3)length的时候会扩容。



这里我们可以看到ThreadLocal是怎么定位一个key在Entry数组中的位置

```
firstKey.threadLocalHashCode & (INITIAL_CAPACITY - 1) 
```

使用一个 static 的原子属性 AtomicInteger nextHashCode，通过每次增加 HASH_INCREMENT = 0x61c88647 ，然后 & (INITIAL_CAPACITY - 1) 取得在数组 private Entry[] table 中的索引。

基本可以将ThreadLocalMap作为一个简单的Map集合看待。



#### **6、ThreadLocal的内存回收**

（1）Thread的回收

threadLocals作为Thread的一个变量，在Thread执行完毕后就会自动回收。



Thread的exit方法如下

```
1.  private void exit() {  

2.       if (group != null) {  

3.           group.threadTerminated(this);  

4.           group = null;  

5.       }  

6.       target = null;  

7.  // 这里线程退出时将threadLocals 置为null

8.       threadLocals = null;  

9.       inheritableThreadLocals = null;  

10.      inheritedAccessControlContext = null;  

11.      blocker = null;  

12.      uncaughtExceptionHandler = null;  

13.  } 
```



（2）ThreadLocalMap的回收

在一个Thread运行时间长的情况下，ThreadLocalMap也会根据情况在线程的生命期内回收ThreadLocalMap 的内存了，不然的话，Entry对象越多，那么ThreadLocalMap就会越来越大，占用的内存就会越来越多，所以对于已经不需要了的线程局部变量，就应该清理掉其对应的Entry对象。

*怎么回收的呢？*

还记得ThreadLocalMap.Entry的key是一个WeakReference对象吗？其实这也是ThreadLocalMap的一个细节，因为**当一个对象仅仅被weak reference指向, 而没有任何其他strong reference指向的时候, 如果GC运行, 那么这个对象就会被回收。**

所以在jvm发生GC的时候，ThreadLocalMap.Entry里面的key会被回收，也就是key被置为null，但是key所在Entry还在存在的，那Entry什么时候回收？



ThreadLocalMap中在执行get、set、remove方法的时候都会对key为null的Entry进行处理

比如get中会清除过期对象

```
1.  private Entry getEntryAfterMiss(ThreadLocal key, int i, Entry e) {  

2.      Entry[] tab = table;  

3.      int len = tab.length;  

4.      while (e != null) {  

5.          ThreadLocal k = e.get();  

6.          if (k == key)  

7.              return e;  

8.         if (k == null) 

9.             expungeStaleEntry(i);  

10.         else  

11.             i = nextIndex(i, len);  

12.         e = tab[i];  

13.     }  

14.     return null;  

15. } 
```



在set中会替换过期对象

```
1.  private void set(ThreadLocal key, Object value) {  

2.       Entry[] tab = table;  

3.       int len = tab.length;  

4.       int i = key.threadLocalHashCode & (len-1);  

5.       for (Entry e = tab[i];  

6.            e != null;  

7.            e = tab[i = nextIndex(i, len)]) {  

8.           ThreadLocal k = e.get();  

9.           if (k == key) {  

10.              e.value = value;  

11.              return;  

12.          }  

13.          if (k == null) { 

14.              replaceStaleEntry(key, value, i);  

15.              return; 

16.          }  

17.      }  

18.      tab[i] = new Entry(key, value);  

19.      int sz = ++size;  

20.      if (!cleanSomeSlots(i, sz) && sz >= threshold)  

21.          rehash();  

22.  } 
```



除此之外当数组长度 > 2/3 最大长度时发生扩容之前会尝试先进行回收

```
1.  if (!cleanSomeSlots(i, sz) && sz >= threshold)  

2.      rehash();  
```



cleanSomeSlots回收方法源码如下：

```
1.  private boolean cleanSomeSlots(int i, int n) {  

2.      boolean removed = false;  

3.      Entry[] tab = table;  

4.      int len = tab.length;  

5.      do {  

6.          i = nextIndex(i, len);  

7.          Entry e = tab[i];  

8.          if (e != null && e.get() == null) {  

9.              n = len;  

10.             removed = true;  

11.             i = expungeStaleEntry(i);  

12.         }  

13.     } while ( (n >>>= 1) != 0);  

14.     return removed;  

15. }  
```



#### **7、ThreadLocal会引起OOM吗？**

理论上是不会的，从上面ThreadLocal的内存回收可以看的出来，无论在线程执行后还是执行中都是会进行回收保障的，但是！如果这个线程一直不退出呢？

没错，就是使用线程池的情况，比如固定线程池，线程一直存活，那么可想而知

如果处理一次业务的时候存放到ThreadLocalMap中一个大对象，处理另一个业务的时候，又一个线程存放到ThreadLocalMap中一个大对象，但是这个线程由于是线程池创建的他会一直存在，不会被销毁，这样的话，以前执行业务的时候存放到ThreadLocalMap中的对象可能不会被再次使用，但是由于线程不会被关闭，因此无法释放Thread中的ThreadLocalMap对象，造成内存溢出。

因此在线程池和ThreadLocal的使用下，是有可能出现OOM溢出的。



但是ThreadLocal出现OOM的原因到底是什么呢？

我们知道ThreadLocalMap threadlocals是Thread的全局变量，**它的生命周期和Thread是一样的**，虽然在ThreadLocalMap.Entry中的key是一个WeakReference，但是也只是在GC的时候清除这个key，然后key所在的Entry对象只会在当前ThreadLocal发生get、set方法后清除，所以如果当前**ThreadLocal在多线程set完大对象之后没有发生get/set行为**，那么这些key为null的Entry就一直存在！



ThreadLoca测试OOM溢出的代码如下：

```
1.  public class ThreadLocalOOM {  

2.      public static void main(String[] args) {  

3.          ExecutorService executorService = Executors.newFixedThreadPool(500);  

4.          ThreadLocal<List<User>> threalLocal = new ThreadLocal<>();  

5.          try {  

6.              for(int i =0; i < 100; i++) {  

7.                  executorService.execute(() ->{  

8.                      threalLocal.set(new ThreadLocalOOM().addBigList());  

9.                      System.out.println(Thread.currentThread().getName() + "has executed!");  

10.                     threalLocal.remove();  

11.                 });  

12.             }  

13.             Thread.sleep(1000L);  

14.         } catch (Exception e) {  

15.             e.printStackTrace();  

16.         }  

17.     }  


18.     public List<User> addBigList(){  

19.         List<User> list = new ArrayList<>(10000);  

20.         for(int j = 0; j < 10000; j++) {  

21.             list.add(new User(Thread.currentThread().getName(),"this is a test User" + j, 18884848, 25545454));  

22.         }  

23.         return list;  

24.     }  

25. }  


26. class User {  

27.     private String name;  

28.     private String description;  

29.     private int age;  

30.     private int sex;  

31.     public User(String name, String description, int age, int sex) {  

32.         super();  

33.         this.name = name;  

34.         this.description = description;  

35.         this.age = age;  

36.         this.sex = sex;  

37.     }  

38. }  
```



这里将Eclipse的Run configuration的jvm参数为-Xms100M -Xmx100M

报错的话是系统没办法在堆内存里面再给ArrayList分配内存了，因为每一个ArrayList都是大对象，然后放到ThreadLocal中又没有清除，所以OOM了。。。



**解决办法就是在使用完ThreadLocal后手动触发回收，也就是ThreadLocal.remove()**

当然这也是建立在业务的基础上的，如果希望ThreadLocal中set的值生命周期变长的话就不能随便remove了，但是要记住，不要给ThreadLocal里面set大对象！