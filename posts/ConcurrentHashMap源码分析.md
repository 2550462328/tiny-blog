ConcurrentHashMap源码分析
2024-08-22
ConcurrentHashMap 是 Java 中的高并发容器。它通过分段锁等机制实现高效的多线程并发操作，支持多线程同时读，写操作也能较好地控制锁粒度，减少争用，确保线程安全，在多线程环境下提供出色的性能表现。
02.jpg
Java基础
huizhang43

首先提出一些问题？

1）多线程操作的时候读写并发吗？

2）每次扩容大小？扩容的时候允许读写吗？

3）多线程怎么帮助扩容？

4）多线程怎么计数的？

5）无锁式实现并发怎么做的？

答案在本文中找.......

Start GO！！！



#### **1、为什么会使用concurrentHashMap这个集合？**

因为传统的hashMap在多线程并发的情况是不安全的，所以使用了concurrentHashMap代替了多线程下的hashMap



#### **2、concurrentHashMap的成员常量**

##### （1）限制值（用于边界值等条件判断）

```
2.  // map的最大容量  

3.  private static final int MAXIMUM_CAPACITY = 1 << 30;   

4.  // map的初始容量  

5.  private static final int DEFAULT_CAPACITY = 16;  

6.  // 虚拟机限制的最大数组长度，用在Collection.toArray()时限制大小  

7.  static final int MAX_ARRAY_SIZE = Integer.MAX_VALUE - 8;  

8.  // map默认并发数(兼容jdk1.7)  

9.  private static final int DEFAULT_CONCURRENCY_LEVEL = 16;  

10. // 扩容因子(兼容jdk1.7),jdk1.8中使用n - ( n \>\> 2)代替 \*0.75f  

11. private static final float LOAD_FACTOR = 0.75f;  

12. // 链表转树的临界节点数  

13. static final int TREEIFY_THRESHOLD = 8;  

14. // 树转链表的临界节点数  

15. static final int UNTREEIFY_THRESHOLD = 6;  

16. // 链表转树时Node[]的长度不小于64  

17. static final int MIN_TREEIFY_CAPACITY = 64;  

18. // 每个线程帮助扩容的时候最少要处理的hash桶数，这个值如果太小会导致多线程竞争数过多  

19. // 在计算的时候 认为一个CPU可以处理8个线程的并发，所以每个线程需要处理的hash桶数是(table.length) / 8 / CPU个数 如果小于 16 就让他等于16  

20. private static final int MIN_TRANSFER_STRIDE = 16;  

21. // 每个扩容都唯一的生成戳的数，最小是6  

22. private static int RESIZE_STAMP_BITS = 16;  

23. // 最大的扩容线程的数量(2\^16 - 1)  

24. private static final int MAX_RESIZERS = (1 \<\< (32 - RESIZE_STAMP_BITS)) - 1;  

25. // 移位量，把生成戳移位后保存在sizeCtl中当做扩容线程计数的基数，向反方向移位后能够反解出生成戳  

26. private static final int RESIZE_STAMP_SHIFT = 32 - RESIZE_STAMP_BITS;

27. // 可使用的CPU内核数

28. static final int NCPU = Runtime.getRuntime().availableProcessors();
```



##### （2）Node节点的hash值相关

```
30. // 下面是一些特殊节点的hash值，正常节点hash在spread函数都会生成正数  

31. // 这个hash值出现在扩容的时候会有一个Forwarding的临时节点，它不存储实际的数据  

32. // 如果旧数组的一个hash桶中全部的节点都迁移到新数组中，旧数组就在这个hash桶中放置一个ForwardingNode  

33. // 读操作或者迭代读时碰到ForwardingNode时，将操作转发到扩容后的新的table数组上去执行，写操作碰见它时，则尝试帮助扩容  

34. static final int MOVED = -1;   

35. // 这个hash值出现在树的头部节点TreeBin，它指向树的根节点root  

36. // TreeBin维护了一个简单读写锁  

37. static final int TREEBIN = -2;   

38. // ReservationNode的hash值，ReservationNode是一个保留节点，相当于一个预留位置，不会保存实际的数据，正常情况是不会出现的  

39. static final int RESERVED = -3;   

40. // 用于和负数hash值进行 & 运算，将其转化为正数（绝对值不相等  

41. static final int HASH_BITS = 0x7fffffff;   
```



#### **3、cocurrentHashMap的成员变量**

##### （1）跟多线程扩容相关

```
44. // 存放node节点的数组  

45. transient volatile Node<K, V>[] table;  


46. /** 扩容后的新的table数组，只有在扩容时才有用 

47.   * nextTable != null，说明扩容方法还没有真正退出，一般可以认为是此时还有线程正在进行扩容 

48.   */  

49. private transient volatile Node<K, V>[] nextTable;  


50.    /** 

51.     * 非常重要的属性 

52.     * sizeCtl = -1，表示有线程正在进行真正的初始化操作 

53.     * sizeCtl = -(1 + nThreads)，表示有nThreads个线程正在进行扩容操作（实际上不是这么计算参与线程的） 

54.     * sizeCtl > 0，表示接下来的真正的初始化操作中使用的容量，或者初始化/扩容完成后的threshold（table.length * 3/4） 

55.     * sizeCtl = 0，默认值，此时在真正的初始化操作中使用默认容量 

56.     */  

57. private transient volatile int sizeCtl;  


58. /** 

59.  * 调整大小时要分割的下一个表索引(上一个transfer任务的起始下标index 加上1)。 

60.  * transfer时方向是从大到小的，迭代时是下标从小往大，二者方向相反，尽量减少扩容时transefer和迭代两者同时处理一个hash桶的情况 

61.  * 顺序相反时，二者相遇过后，迭代没处理的都是已经transfer的hash桶，transfer没处理的，都是已经迭代的hash桶，冲突会变少 

62.  * 下标在[nextIndex - 实际的stride （下界要 >= 0）, nextIndex - 1]内的hash桶，就是每个transfer的任务区间 

63.  * 每次接受一个transfer任务，都要CAS执行 transferIndex = transferIndex - 实际的stride，保证一个transfer任务不会被几个线程同时获取（相当于任务队列的size减1） 

64.  * 当没有线程正在执行transfer任务时，一定有transferIndex <= 0，这是判断是否需要帮助扩容的重要条件（相当于任务队列为空） 

65.  */  

66. private transient volatile int transferIndex;  
```



##### （2）跟高效的并发计数方式有关

```
68. // 下面三个主要与统计数目有关，可以参考jdk1.8新引入的java.util.concurrent.atomic.LongAdder的源码，帮助理解  

69. // 计数器基本值，主要在没有碰到多线程竞争时使用，需要通过CAS进行更新  

70. private transient volatile long baseCount;  


71. // CAS自旋锁标志位，用于初始化，或者counterCells扩容时  

72. private transient volatile int cellsBusy;  


73. // 用于高并发的计数单元，如果初始化了这些计数单元，那么跟table数组一样，长度必须是2^n的形式  

74. private transient volatile CounterCell[] counterCells;  
```



#### **4、concurrentHashMap的构造函数**

Jdk1.8的构造函数是不带loadFactor的，带loadFactor是为了向下兼容jdk1.7

```
1.  public ConcurrentHashMapDebug(int initialCapacity) {  

2.      if (initialCapacity < 0)  

3.          throw new IllegalArgumentException();  

4.      int cap = ((initialCapacity >= (MAXIMUM_CAPACITY >>> 1)) ? MAXIMUM_CAPACITY  

5.              : tableSizeFor(initialCapacity + (initialCapacity >>> 1) + 1));  

6.      this.sizeCtl = cap;  

7.  }  

8.  public ConcurrentHashMapDebug(Map<? extends K, ? extends V> m) {  

9.      this.sizeCtl = DEFAULT_CAPACITY;  

10.     putAll(m);  

11. }  
```

可以看到在构造函数中没有初始化table数组，将sizeCtrl值设为cap



#### **5、concurrentHashMap的内部类**

![img](http://pcc.huitogo.club/6dfd2b8ff985c4540a44cea5c94da2c8)



#### **6、concurrentHashMap的cas方法**

```
3. // 用来返回节点数组的指定位置的节点的原子操作  

4.  static final <K, V> Node<K, V> tabAt(Node<K, V>[] tab, int i) {  

5.      return (Node<K, V>) U.getObjectVolatile(tab, ((long) i << ASHIFT) + ABASE);  

6.  }  


7.  // cas操作，用来在指定位置修改值  

8.  static final <K, V> boolean casTabAt(Node<K, V>[] tab, int i, Node<K, V> c, Node<K, V> v) {  

9.      return U.compareAndSwapObject(tab, ((long) i << ASHIFT) + ABASE, c, v);  

10. }  


11. // 原子操作，在指定位置设置值  

12. static final <K, V> void setTabAt(Node<K, V>[] tab, int i, Node<K, V> v) {  

13.     U.putObjectVolatile(tab, ((long) i << ASHIFT) + ABASE, v);  

14. }  
```

可以看到底层都是通过Unsafe类实现cas操作的



#### **7、concurrentHashMap的putVal()方法**

为什么单独讲这个方法呢，因为这个方法算是concurrentHashMap的一个核心，多线程情况下对于concurrentHashMap来说主要的竞争就是写写竞争，还包括单线程初始化table、多线程帮助扩容、并发计数等核心操作。



除了一些核心操作外，跟HashMap还是类似的（链表和红黑树的操作），可以参考HashMap的源码来学习。

putVal的源码如下：

```
1.  final V putVal(K key, V value, boolean onlyIfAbsent) {   

2.      if (key == null || value == null)  

3.          throw new NullPointerException();  

4.      int hash = spread(key.hashCode());  // 计算key的hash值  

5.      int binCount = 0; // 单个链表上元素的个数  

6.      for (Node<K, V>[] tab = table;;) {   

7.          Node<K, V> f; // 计算key后下标的Node  

8.          int n, i, fh;  // n是table长度  i是key所在链表在node数组中的下标  fh是Node的hash值  

9.          if (tab == null || (n = tab.length) == 0) // 如果node数组为空，初始化数组  

10.             tab = initTable();   

11.         else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) { // 如果计算的Key所在的位置为空，直接添加  

12.             if (casTabAt(tab, i, null, new Node<K, V>(hash, key, value, null)))   

13.                 break;   

14.         } else if ((fh = f.hash) == MOVED) // 如果检测到某个节点的hash值是MOVED，则表示正在进行数组扩张的数据复制阶段  

15.             tab = helpTransfer(tab, f);  // 则当前线程也会参与去复制，通过允许多线程复制的功能，一次来减少数组的复制所带来的性能损失  

16.         else { // 如果计算的key所在的位置有值的话  

17.             V oldVal = null;  

18.             synchronized (f) { // 给这个Node加锁  

19.                 if (tabAt(tab, i) == f) { // 再次确认之前计算下标取出的Node还是那个位置  

20.                     if (fh >= 0) { // fh >= 0 时 Node所在的位置是一个链表，fh = -2时是一个树  

21.                         binCount = 1; //自身一个Node，所以所在链表初始长度为1  

22.                         for (Node<K, V> e = f;; ++binCount) { // 遍历链表  

23.                             K ek;  

24.                             if (e.hash == hash && ((ek = e.key) == key || (ek != null && key.equals(ek)))) { // 如果取出的Node刚好Key就是要新增的key  

25.                                 oldVal = e.val;  

26.                                 if (!onlyIfAbsent) // 没有存在不可替换选项时，覆盖旧value  

27.                                     e.val = value;  

28.                                 break;  

29.                             }  

30.                             Node<K, V> pred = e;  

31.                             if ((e = e.next) == null) { // 如果取出的Node的Key不是要新增的key  

32.                                 pred.next = new Node<K, V>(hash, key, value, null); // 将新增的node放到尾部  

33.                                 break;  

34.                             }  

35.                         }  

36.                     } else if (f instanceof TreeBin) { // Node所在的位置是一棵树  

37.                         Node<K, V> p;  

38.                         binCount = 2;  // 树的头节点+自身，所以所在链表初始长度为2  

39.                         if ((p = ((TreeBin<K, V>) f).putTreeVal(hash, key, value)) != null) { // 将新节点添加到树中  

40.                             oldVal = p.val;  

41.                             if (!onlyIfAbsent)  

42.                                 p.val = value;  

43.                         }  

44.                     }  

45.                 }  

46.             }  

47.             if (binCount != 0) {  

48.                 if (binCount >= TREEIFY_THRESHOLD) // 判断是要转换成树还是扩容数组  

49.                     treeifyBin(tab, i);  

50.                 if (oldVal != null)  

51.                     return oldVal; // 返回的替换前的旧值  

52.                 break;  

53.             }  

54.         }  

55.     }  

56.     addCount(1L, binCount); // 并发计数  

57.     return null;  

58. }  
```



上面代码分成下面步骤

1） table未初始化，进行单线程初始化

2）table初始化了，经计算放置Node的下标处为null，直接cas放置值

3）table初始化了，经计算放置Node的下标处有节点，但节点的hash值为MOVED（表示table数组正在扩容），那么此时放弃添加，帮助扩容（到下个循环在添加）。

4）table初始化了，节点的hash值不为MOVED，这个时候就把存在的节点synchronized，判断是链表还是树（进行添加）。

5）判断链表上的个数，如果超过8 是扩容还是转红黑树。

6）因为添加了一个值，就要进行计数（+1）。



看完步骤再细看方法

##### **（1）initTable()**

初始化数组，保证单线程进行

```
1.  /** 

2.     * 初始化数组table， 

3.     * 如果sizeCtl小于0，说明别的数组正在进行初始化，则让出执行权 

4.     * 如果sizeCtl大于0的话，则初始化一个大小为sizeCtl的数组 

5.     * 否则的话初始化一个默认大小(16)的数组 

6.     * 然后设置sizeCtl的值为数组长度的3/4 

7.     */  

8.  private final Node<K, V>[] initTable() {  

9.      Node<K, V>[] tab;  

10.     int sc;  

11.     while ((tab = table) == null || tab.length == 0) {  

12.         if ((sc = sizeCtl) < 0) //小于0的时候表示在别的线程在初始化表或扩展表，要保证单线程扩容，进行线程礼让  

13.             Thread.yield();   

14.         else if (U.compareAndSwapInt(this, SIZECTL, sc, -1)) { //尝试cas修改sizeCtl(类似加锁) 设定为-1表示要初始化表了  

15.             try {  

16.                 if ((tab = table) == null || tab.length == 0) {  

17.                     int n = (sc > 0) ? sc : DEFAULT_CAPACITY;  

18.                     @SuppressWarnings("unchecked")  

19.                     Node<K, V>[] nt = (Node<K, V>[]) new Node<?, ?>[n];  

20.                     table = tab = nt;  

21.                     sc = n - (n >>> 2);  //初始化后，sizeCtl长度为数组长度的3/4  

22.                 }  

23.             } finally {  

24.                 sizeCtl = sc;   

25.             }  

26.             break;  

27.         }  

28.     }  

29.     return tab;  

30. }  
```



##### **（2）spread(key.hashCode())**

计算key的hash散列值

```
1.  static final int spread(int h) {  

2.      return (h ^ (h >>> 16)) & HASH_BITS;  // HASH_BITS =  1111111111111111111111111111111

3.  }
```

这里将（h >>> 16）^ h就是将key的hash值的高16位跟低16位进行异或，跟hashMap中操作一样，但是这里多了一个逻辑与运算。这里是**为了防止前面的异或操作出现负数的情况**，保证spread方法的返回值是一个正数。试想如果异或结果是-1或者-2的话不就跟特殊Node的Hash值冲突了么？



##### **（3）helpTransfer(Node<K, V>[] tab, Node<K, V> f)**

多线程帮助扩容

```
1.  final Node<K, V>[] helpTransfer(Node<K, V>[] tab, Node<K, V> f) {  

2.      Node<K, V>[] nextTab;  

3.      int sc;  

4.      if (tab != null && (f instanceof ForwardingNode) && (nextTab = ((ForwardingNode<K, V>) f).nextTable) != null) {  

5.          int rs = resizeStamp(tab.length); // 通过resizeStamp生成唯一戳，来保证这次扩容的唯一性，防止出现扩容重叠的现象  

6.          while (nextTab == nextTable && table == tab && (sc = sizeCtl) < 0) {  

7.              if ((sc >>> RESIZE_STAMP_SHIFT) != rs || sc == rs + 1 || sc == rs + MAX_RESIZERS || transferIndex <= 0)  

8.                  break;  

9.              if (U.compareAndSwapInt(this, SIZECTL, sc, sc + 1)) {  

10.                 transfer(tab, nextTab); // 将tab扩容到nextTab  

11.                 break;  

12.             }  

13.         }  

14.         return nextTab;  

15.     }  

16.     return table;  

17. }  
```



**这里需要先搞清楚的是rs是什么？sc又是什么？**

**rs = resizeStamp(tab.length);**

```
1.  /** 

2.   * 返回与扩容有关的一个生成戳rs，每次新的扩容，都有一个不同的n，这个生成戳就是根据n来计算出来的一个数字，n不同，这个数字也不同 

3.   * 保证 rs << RESIZE_STAMP_SHIFT（16） 必须是负数 

4.   * numberOfLeadingZeros方法返回无符号整型i的最高非零位前面的0的个数，包括符号位在内，如果是负数直接返回0 

5.   */  

6.  static final int resizeStamp(int n) {  

7.      return Integer.numberOfLeadingZeros(n) | (1 << (RESIZE_STAMP_BITS - 1));  

8.  }  
```



这里1 << (RESIZE_STAMP_BITS - 1)就是2^15 (1000 0000 0000 0000)

Integer.numberOfLeadingZeros(n) 表示int（32位）类型n的最高非零位前面的0的个数

![img](http://pcc.huitogo.club/b876356bfc821fa6cd7577f9bd5f7269)

两者进行逻辑或操作的话，会让Integer.numberOfLeadingZeros(n)结果的第16个位置为1，当n为32的时候，rs就是1000 0000 0001 1010 （32794）

如果将rs << RESIZE_STAMP_BITS（16）的话，即第32位为1（符号位），所以必是负数



**sc就是sizeCtrl**

源码注释解释说：sizeCtl = -(1 + nThreads)，表示有nThreads个线程正在进行扩容操作（实际上不是这么计算参与线程的）

在tryPresize中，第一条扩容线程会将sizeCtl变成(rs << RESIZE_STAMP_SHIFT) + 2)，sizeCtl就是在这个时候变成负数（除了初始化table的时候变成 - 1除外）。

```
U. compareAndSwapInt(this, SIZECTL, sc, (rs << RESIZE_STAMP_SHIFT) + 2)
```



上面说了rs<<16后一定是一个负数，sizeCtrl此时一定是一个负数，所以

A. sizeCtrl的高16位就是rs

B. sizeCtrl的低16位就是扩容的线程数 + 1，上面 + 2 表示此时有一个线程在扩容



这个时候就可以过来理解helpfer的源码了：

1）判断当前table正在扩容（ForwardindNode只在扩容的时候出现）。

2）再判断当前是多线程在扩容中（sizeCtl < 0）

3）在帮助扩容之前还有几个前提条件，也就是如何理解这4个if

　A. **（sc>>>RESIZE_STAMP_SHIFT） != rs**：sc >>>16 就是rs了，如果两者不相等，说明底层数组的长度改变了，说明扩容结束了，所以直接跳出循环，不在需要进行协助扩容了

　B. **transferIndex <= 0**：表示所有的transfer任务都被领取光了，没有剩余的hash桶给自己这个线程来transfer，此时线程不能再帮助扩容了

　C. **sc == rs + 1**：表示扩容线程已经达到最大值，在ConcurrentHashMap永远不相等。

　D. **sc == rs + MAX_RESIZERS**：表示扩容线程已经达到最大值，在ConcurrentHashMap永远不相等

4）4个if条件后就进入扩容环节了（领取任务），当然前提要将sc + 1（多了一个线程参与扩容）。



##### **（4）treeifyBin(Node<K, V>[] tab, int index)**

将tab扩容或者在index处的链表转红黑树

```
1.  private final void treeifyBin(Node<K, V>[] tab, int index) {  //TODO  

2.      Node<K, V> b;  

3.      @SuppressWarnings("unused")  

4.      int n, sc;  

5.      if (tab != null) {  

6.          if ((n = tab.length) < MIN_TREEIFY_CAPACITY)  

7.              tryPresize(n << 1);   // 扩容  

8.          else if ((b = tabAt(tab, index)) != null && b.hash >= 0) {  

9.              synchronized (b) {  

10.                 if (tabAt(tab, index) == b) {  

11.                     TreeNode<K, V> hd = null, tl = null; // hd 头节点 tl 尾节点  

12.                     for (Node<K, V> e = b; e != null; e = e.next) {   

13.                         TreeNode<K, V> p = new TreeNode<K, V>(e.hash, e.key, e.val, null, null);  

14.                         if ((p.prev = tl) == null)  

15.                             hd = p;  

16.                         else  

17.                             tl.next = p;  

18.                         tl = p;  

19.                     }  

20.                     setTabAt(tab, index, new TreeBin<K, V>(hd)); //将链表转换后的红黑树的头节点放在table的index所在的位置  

21.                 }  

22.             }  

23.         }  

24.     }  

25. }  
```



这里的tryPresize(n << 1) 扩容方法下面再讲，判断链表转红黑树的时候需要知道Node数组有个桶是红黑树的话，这个桶在Node数组上的头节点不是root节点，而是一个TreeBin。

```
setTabAt(tab, index, new TreeBin<K, V>(hd))
```

这里TreeBin + TreeNode 的功能相当于hashMap中的TreeNode，TreeBin指向root节点



**这里为什么用TreeBin呢？**

TreeBin的源码：

```
1.  static final class TreeBin<K, V> extends Node<K, V> {  

2.      TreeNode<K, V> root;  

3.      volatile TreeNode<K, V> first;  

4.      volatile Thread waiter;  

5.      volatile int lockState;  

6.      static final int WRITER = 1; // 写锁  

7.      static final int WAITER = 2; // 等待中  

8.      static final int READER = 4; // 读写锁  

9.      TreeBin(TreeNode<K, V> b) {  

10.         super(TREEBIN, null, null, null);  

11.         // ...  

12.     }  


13.     private final void lockRoot() {  

14.         if (!U.compareAndSwapInt(this, LOCKSTATE, 0, WRITER))  

15.             contendedLock(); // offload to separate method  

16.     }  


17.     private final void unlockRoot() {  

18.         lockState = 0;  

19.     }  


20.     private final void contendedLock() {  

21.         boolean waiting = false;  

22.         for (int s;;) {  

23.             if (((s = lockState) & ~WAITER) == 0) {  

24.                 if (U.compareAndSwapInt(this, LOCKSTATE, s, WRITER)) {  

25.                     if (waiting)  

26.                         waiter = null;  

27.                     return;  

28.                 }  

29.             } else if ((s & WAITER) == 0) {  

30.                 if (U.compareAndSwapInt(this, LOCKSTATE, s, s | WAITER)) {  

31.                     waiting = true;  

32.                     waiter = Thread.currentThread();  

33.                 }  

34.             } else if (waiting)  

35.                 LockSupport.park(this);  
```

从上面大概源码中我们知道这里是利用**TreeBin维护了一个简单的读写锁**，在putTreeVal和removeTreeNode方法中使用到。



##### **（5）tryPresize(int size)**

进行扩容（并非扩容的实际代码）

源码如下：

```
1.  private final void tryPresize(int size) {    

2.      int c = (size >= (MAXIMUM_CAPACITY >>> 1)) ? MAXIMUM_CAPACITY : tableSizeFor(size + (size >>> 1) + 1);  

3.      int sc;  

4.      while ((sc = sizeCtl) >= 0) {  // 这里一直获取最新得sizeCtl 直到“拿到锁”，compareAndSwapInt替换成功  

5.          Node<K, V>[] tab = table;  

6.          int n;  

7.          if (tab == null || (n = tab.length) == 0) {  // 出现tab为null的情况就是初始化map用的是传入一个Map,这样一上来就得扩容数组，从而tab都是空得  

8.              n = (sc > c) ? sc : c; // sc理论上是小于c的，大于c的情况仅限于上面的情况，sc = Default_Capablity 而size是传入map的size  

9.              if (U.compareAndSwapInt(this, SIZECTL, sc, -1)) {  

10.                 try {  

11.                     if (table == tab) {  

12.                         @SuppressWarnings("unchecked")  

13.                         Node<K, V>[] nt = (Node<K, V>[]) new Node<?, ?>[n];   

14.                         table = nt;  

15.                         sc = n - (n >>> 2); // sizeCtl = table.length * (3/4)  

16.                     }  

17.                 } finally {  

18.                     sizeCtl = sc;  

19.                 }  

20.             }  

21.         } else if (c <= sc || n >= MAXIMUM_CAPACITY)  

22.             break;  

23.         else if (tab == table) {  

24.             int rs = resizeStamp(n); // ???  计算本次扩容的生成戳  rs >>> RESIZE_STAMP_SHIFT 必是负数   

25.             if (sc < 0) { // 如果正在扩容Table的话，则帮助扩容  

26.                 Node<K, V>[] nt;  

27.                 if ((sc >>> 2) != rs || sc == rs + 1 || sc == rs + MAX_RESIZERS || (nt = nextTable) == null || transferIndex <= 0) // MAX_RESIZERS是最大扩容的数量  

29.                     break;  

30.                 if (U.compareAndSwapInt(this, SIZECTL, sc, sc + 1)) // 这里的sc是线程数 多线程帮助扩容  

31.                     transfer(tab, nt); // 将第一个参数的table中的元素，移动到第二个元素的table中去，  

32.             } else if (U.compareAndSwapInt(this, SIZECTL, sc, (rs << RESIZE_STAMP_SHIFT) + 2)) // 试着让自己成为第一个执行transfer任务的线程  

33.                 transfer(tab, null); // 当第二个参数为null的时候，会创建一个两倍大小的table  

34.         }  

35.     }  

36. }  
```



上述步骤流程如下：

1）先判断这次扩容是不是putAll引起的，也就是table是空的，如果是的话，我扩容的大小就是大于map.size * 2 + map.size + 1的最小2的幂次数，这里map是putAll时的map参数，同时是map.size < MAXIMUM_CAPACITY(2 ^ 30)的前提下。

2） 如果不是putAll引起的，就是实打实的想扩容，那么判断下现在有没有线程正在扩容

3）有线程扩容，就helpTransfer（帮助扩容），将tab扩容成nextTable，这里和helpTransfer代码有一点不一样的就是if中加了一个判断条件(nt = nextTable) == null ：表示整个扩容过程已经结束，或者扩容过程处于一个单线程的阶段（transfer方法中创建nextTable是由单线程完成的），此时不能帮助扩容。

4）当前没有其他线程正在扩容，尝试将自己设置为第一个扩容的，就是设置sizeCtl的值为 (rs << RESIZE_STAMP_SHIFT) + 2，这时候nextTable是null的，所以这时候扩容的大小也就是tab.length * 2（原大小的两倍）。



##### **（6）transfer(Node<K, V>[] tab, Node<K, V>[] nextTab)**

这个就是扩容的实质性代码了

```
1.  private final void transfer(Node<K, V>[] tab, Node<K, V>[] nextTab) { // TODO  

2.      int n = tab.length, stride;  

3.      if ((stride = (NCPU > 1) ? (n >>> 3) / NCPU : n) < MIN_TRANSFER_STRIDE)  

4.          stride = MIN_TRANSFER_STRIDE;   

5.      if (nextTab == null) { // 如果new tab为空的话 就初始化一个两倍于原table的数组  

6.          try {  

7.              @SuppressWarnings("unchecked")  

8.              Node<K, V>[] nt = (Node<K, V>[]) new Node<?, ?>[n << 1];  

9.              nextTab = nt;  

10.         } catch (Throwable ex) { //处理内存不足导致的OOM，以及table数组超过最大长度，这两种情况都实际上无法再进行扩容了  

11.             sizeCtl = Integer.MAX_VALUE;  

12.             return;  

13.         }  

14.         nextTable = nextTab;  

15.         transferIndex = n;  

16.     }  

17.     int nextn = nextTab.length;  

18.   // 转发节点，在旧数组的一个hash桶中所有节点都被迁移完后，放置在这个hash桶中，表明已经迁移完，对它的读操作会转发到新数组  

19.     ForwardingNode<K, V> fwd = new ForwardingNode<K, V>(nextTab);  

20.     boolean advance = true;  

21.     boolean finishing = false; // to ensure sweep before committing nextTab  


22.     for (int i = 0, bound = 0;;) {  

23.         Node<K, V> f;  

24.         int fh;  

25.         while (advance) {  // 这里相当于每个线程领取任务  

26.             int nextIndex, nextBound;  

27.             if (--i >= bound || finishing) // 一次transfer任务还没有执行完毕  

28.                 advance = false;  

29.             else if ((nextIndex = transferIndex) <= 0) { // transfer任务已经没有了，表明可以准备退出扩容了  

30.                 i = -1;  

31.                 advance = false;  

32.             } else if (U.compareAndSwapInt(this, TRANSFERINDEX, nextIndex,  

33.                     nextBound = (nextIndex > stride ? nextIndex - stride : 0))) { // // 尝试申请一个transfer任务  

34.                 bound = nextBound; // 申请到任务后标记自己的任务区间 bound = nextIndex - stride  

35.                 i = nextIndex - 1;  

36.                 advance = false;  

37.             }  

38.         }  


39.         if (i < 0 || i >= n || i + n >= nextn) {  // 处理扩容重叠  

40.             int sc;  

41.             if (finishing) {  

42.                 nextTable = null;  

43.                 table = nextTab;  

44.                 sizeCtl = (n << 1) - (n >>> 1);  

45.                 return;  

46.             }  

47.             if (U.compareAndSwapInt(this, SIZECTL, sc = sizeCtl, sc - 1)) {  

48.                 if ((sc - 2) != resizeStamp(n) << RESIZE_STAMP_SHIFT)  

49.                     return;  

50.                 finishing = advance = true;  

51.                 i = n; // recheck before commit  

52.             }  

53.         } else if ((f = tabAt(tab, i)) == null) //  hash桶本身为null，不用迁移，直接尝试安放一个转发节点  

54.             advance = casTabAt(tab, i, null, fwd);  

55.         else if ((fh = f.hash) == MOVED)  

56.             advance = true; // already processed  

57.         else {   

58.             synchronized (f) {    

59.                 if (tabAt(tab, i) == f) {   

60.                     Node<K, V> ln, hn;  

61.                     if (fh >= 0) { //链表处理  

62.                            /* 

63.                             * 因为n的值为数组的长度，且是power(2,x)的，所以，在&操作的结果只可能是0或者n 

64.                             * 根据这个规则 

65.                             *         0-->  放在新表的相同位置 

66.                             *         n-->  放在新表的（n+原来位置） 

67.                             *         'rehash（重新散列）'的操作跟hashMap一样 

68.                             */  

69.                         int runBit = fh & n;    

70.                         Node<K, V> lastRun = f;  

71.                          /* 

72.                             * lastRun 表示的是需要复制的最后一个节点 

73.                             * 每当新节点的hash&n -> b 发生变化的时候，就把runBit设置为这个结果b 

74.                             * 这样for循环之后，runBit的值就是最后不变的hash&n的值 

75.                             * 而lastRun的值就是最后一次导致hash&n 发生变化的节点(假设为p节点) 

76.                             * 为什么要这么做呢？因为p节点后面的节点的hash&n 值跟p节点是一样的， 

77.                             * 所以在复制到新的table的时候，它肯定还是跟p节点在同一个位置 

78.                             * 在复制完p节点之后，p节点的next节点还是指向它原来的节点，就不需要进行复制了，自己就被带过去了 

79.                             * 这也就导致了一个问题就是复制后的链表的顺序并不一定是原来的倒序 

80.                             */  

81.                         for (Node<K, V> p = f.next; p != null; p = p.next) {  

82.                             int b = p.hash & n;  

83.                             if (b != runBit) {  

84.                                 runBit = b;  

85.                                 lastRun = p;  

86.                             }  

87.                         }  

88.                         if (runBit == 0) { // (注一) 这里可以认为设置完runBit = 0之后的节点都是不用复制到新数组的  

89.                             ln = lastRun;  

90.                             hn = null;  

91.                         } else { // （注二）这里可以认为设置完runBit != 0之后的节点都是需要复制到新数组的  

92.                             hn = lastRun;  

93.                             ln = null;  

94.                         }  

95.                         for (Node<K, V> p = f; p != lastRun; p = p.next) { // 这里轮询链表节点p，根据(ph & n) == 0判断是否要复制  

96.                             int ph = p.hash;  

97.                             K pk = p.key;  

98.                             V pv = p.val;  

99.                             if ((ph & n) == 0)  

100.                                 ln = new Node<K, V>(ph, pk, pv, ln); // 将不需要复制的节点放在上述(注一) lastRun的前面，如果为空相当于重新构建一个链表  

101.                             else  

102.                                 hn = new Node<K, V>(ph, pk, pv, hn); //将需要复制的节点放在上述(注二) lastRun的前面，如果为空相当于重新构建一个链表  

103.                         }  

104.                         setTabAt(nextTab, i, ln); // 将ln所在的链表放置在原地  

105.                         setTabAt(nextTab, i + n, hn); // 将hn所在的链表放在在原地 + n的位置  

106.                         setTabAt(tab, i, fwd); // 在旧tab的位置 放置 ForwardingNode节点  

107.                         advance = true; //进入下一个循环  

108.                     } else if (f instanceof TreeBin) { // 红黑树处理  

109.                         TreeBin<K, V> t = (TreeBin<K, V>) f;  

110.                         TreeNode<K, V> lo = null, loTail = null; //  

111.                         TreeNode<K, V> hi = null, hiTail = null;  

112.                         int lc = 0, hc = 0;  

113.                         for (Node<K, V> e = t.first; e != null; e = e.next) {  

114.                             int h = e.hash;  

115.                             TreeNode<K, V> p = new TreeNode<K, V>(h, e.key, e.val, null, null);  

116.                             if ((h & n) == 0) { // 将不需要复制的节点 整合到 lo ~ loTail上  

117.                                 if ((p.prev = loTail) == null)  

118.                                     lo = p;  

119.                                 else  

120.                                     loTail.next = p;  

121.                                 loTail = p;  

122.                                 ++lc;  

123.                             } else { // 将需要复制的节点 整合到 hi ~ hiTail上  

124.                                 if ((p.prev = hiTail) == null)  

125.                                     hi = p;  

126.                                 else  

127.                                     hiTail.next = p;  

128.                                 hiTail = p;  

129.                                 ++hc;  

130.                             }  

131.                         }  


132.                         // 判断新生成的两个红黑树 是否要转成链表  

133.                         ln = (lc <= UNTREEIFY_THRESHOLD) ? untreeify(lo) : (hc != 0) ? new TreeBin<K, V>(lo) : t;  

134.                         hn = (hc <= UNTREEIFY_THRESHOLD) ? untreeify(hi) : (lc != 0) ? new TreeBin<K, V>(hi) : t;  

135.                         setTabAt(nextTab, i, ln);  

136.                         setTabAt(nextTab, i + n, hn);  

137.                         setTabAt(tab, i, fwd);  

138.                         advance = true;  

139.                     }  

140.                 }  

141.             }  

142.         }  

143.     }  
```



上述扩容的步骤可以解释如下：

1）先计算每个线程需要处理的桶数（这里叫stride）

2）判断新的table是否为空，如果为空就整一个原来tab两倍的容器。

3）再进入循环，每个线程申领自己的任务，（transferIndex~transferIndex-stride）之间的桶数就是该线程的转移任务。每完成一个桶判断一下任务完成没有（是否到达了bound），如果完成了是否还能再申领任务，需要注意的是这里**处理桶数是从后往前进行处理**，迭代遍历是从前往后遍历，可以有效解决扩容时进行迭代引起的冲撞，如果冲撞了就找到放置在旧tab的ForwardingNode节点，通过它找到newTable。

4）领完任务之后需要预防一下**扩容重叠**的问题，简单的来解释就是线程A正在将数组从n->2n进行扩容（在处理中），线程B也在将数组从n->2n进行扩容，然后线程B成功扩容完了结束线程。这时候线程C要将数组从2n->4n扩容，然后线程A扩容完了，想要再领任务，这时候领的任务是从2n->4n了，但是线程A中的还是n->2n得目标，所以扩容重叠，具体可以看下面得解释。

5）线程处理任务之前需要思考一下，先是如果正在处理的桶中没有数据，直接在这个地方放一个ForwardingNode节点，然后就是这个桶是不是被别人处理过了，这时候转到下一个桶。



6）下面是线程处理任务的正式环节了，需要分别处理链表和红黑树的情况

A. 桶中的是链表，这时候仍然利用好hashMap中的优良写法，直接key.hash & tab.length == 0判断Node需不需要搬家（搬到tab.length + 当前位置）

这里有一个优化的地方就是我假设链表的后面一串都是要复制的，或者都不需要复制的，那么我就不需要大张旗鼓的一个个处理后面这些了，直接找到他们的头，让它加入我们新构建的链表，这样它的小弟就屁颠屁颠的过来了（代码中的runBit就是那个分界线）。然后在newTable放置好新构建的需要复制的链表和不需要复制的链表就阔以咯。

B. 桶中的红黑树，对待红黑树就没有上面那个骚操作了，老老实实的构建需要复制的红黑树和不需要复制的红黑树，然后放置进newTable。这里需要注意的就是红黑树需不要降解成链表的问题。



构建的过程，如图：

![img](http://pcc.huitogo.club/6ff664fd81123ac93d7abf585ddfd318)



##### **（7）addCount(long x, int check)**

高并发计数的方法

源码如下：

```
1.  private final void addCount(long x, int check) {  

2.      CounterCell[] as;  

3.      long b, s;    

4.      // counterCells不为null的时候代表这时候是有冲突的  

5.      // 所以在尝试修改baseCount基础值失败后进入并发计数模式，也就是调用fullAddCount  

6.      if ((as = counterCells) != null || !U.compareAndSwapLong(this, BASECOUNT, b = baseCount, s = b + x)) {  

7.          CounterCell a;  

8.          long v;  

9.          int m;  

10.         boolean uncontended = true;  

11.         if (as == null || (m = as.length - 1) < 0 || (a = as[ThreadLocalRandom.getProbe() & m]) == null  

12.                 || !(uncontended = U.compareAndSwapLong(a, CELLVALUE, v = a.value, v + x))) {  

13.             fullAddCount(x, uncontended); // 这里跟LongAdder是一样的，可以去看LongAdder源码分析  

14.             return;   

15.         }  

16.         if (check <= 1)  

17.             return;  

18.         s = sumCount();  

19.     }  

20.     if (check >= 0) { // check是桶中的Node数量，这里判断是否要扩容，代码类似helpTransfer  

21.         Node<K, V>[] tab, nt;  

22.         int n, sc;  

23.         while (s >= (long) (sc = sizeCtl) && (tab = table) != null && (n = tab.length) < MAXIMUM_CAPACITY) {  

24.             int rs = resizeStamp(n);  

25.             if (sc < 0) {  

26.                 if ((sc >>> RESIZE_STAMP_SHIFT) != rs || sc == rs + 1 || sc == rs + MAX_RESIZERS  

27.                         || (nt = nextTable) == null || transferIndex <= 0)  

28.                     break;  

29.                 if (U.compareAndSwapInt(this, SIZECTL, sc, sc + 1))  

30.                     transfer(tab, nt);  

31.             } else if (U.compareAndSwapInt(this, SIZECTL, sc, (rs << RESIZE_STAMP_SHIFT) + 2))  

32.                 transfer(tab, null);  

33.             s = sumCount();  

34.         }  

35.     }  

36. }  
```



这里如果看了俺的LongAdder源码分析的话也是很简单的

流程步骤如下

1）先试着去修改baseCount的值（+1），看过sumCount的源码知道concurrentHash的size就是baseCount + CounterCell[]的值，如果修改失败就是有冲突了，这时候调用fullAddCount()，其实就是Striped64.longAccumulate()，进行累积值。

2）再判断新增后是否要扩容，走的就是helpTransfer代码，没线程就自己扩容，有线程就帮助扩容。



#### **8、总结一下concurrentHashMap的同步机制**

首先是读操作，从源码中可以看出来，在get操作中，根本没有使用同步机制，也没有使用unsafe方法，所以读操作是支持并发操作的。

那么写操作呢？

分析这个之前，先看看什么情况下会引起数组的扩容，扩容是通过transfer方法来进行的。而调用transfer方法的只有trePresize、helpTransfer和addCount三个方法。

这三个方法又是分别在什么情况下进行调用的呢？

　1）tryPresize是在treeIfybin和putAll方法中调用，treeIfybin主要是在put添加元素完之后，判断该数组节点相关元素是不是已经超过8个的时候，如果超

　过则会调用这个方法来扩容数组或者把链表转为树。

　2）helpTransfer是在当一个线程要对table中元素进行操作的时候，如果检测到节点的HASH值为MOVED的时候，就会调用helpTransfer方法，在

　helpTransfer中再调用transfer方法来帮助完成数组的扩容

　3）addCount是在当对数组进行操作，使得数组中存储的元素个数发生了变化的时候会调用的方法。



**所以引起数组扩容的情况如下：**

1）只有在往map中添加元素的时候，在某一个节点的数目已经超过了8个，同时数组的长度又小于64的时候，才会触发数组的扩容。

2）当数组中元素达到了sizeCtl的数量的时候，则会调用transfer方法来进行扩容



**那么在扩容的时候，可以不可以对数组进行读写操作呢？**

事实上是可以的。当在进行数组扩容的时候，如果当前节点还没有被处理（也就是说还没有设置为fwd节点），那就可以进行设置操作。

如果该节点已经被处理了，则当前线程也会加入到扩容的操作中去。



**那么，多个线程又是如何同步处理的呢？**

在ConcurrentHashMap中，同步处理主要是通过Synchronized和unsafe两种方式来完成的。

1）在取得sizeCtl、某个位置的Node的时候，使用的都是unsafe的方法，来达到并发安全的目的。

2）当需要在某个位置设置节点的时候，则会通过Synchronized的同步机制来锁定该位置的节点。

3）在数组扩容的时候，则通过处理的步长和fwd节点来达到并发安全的目的，通过CAS设置hash值为MOVED。

4）当把某个位置的节点复制到扩张后的table的时候，也通过Synchronized的同步机制来保证线程安全。