Vue入门扫盲总结
2024-08-22
Vue 是一款流行的前端 JavaScript 框架。它采用数据驱动视图的方式，通过简洁的模板语法将数据与页面进行绑定。Vue 易于上手，具有高效的响应式系统，能自动更新页面。同时，它还支持组件化开发，提升代码复用性和可维护性。
05.jpg
大前端
huizhang43

### 1、vue实例的生命周期



![img](http://pcc.huitogo.club/cbdce8588b13c236cf993a71de9fd33c)



vue生命周期分为四个阶段

第一阶段（创建阶段）：beforeCreate，created

第二阶段（挂载阶段）：beforeMount（render），mounted

第三阶段（更新阶段）：beforeUpdate，updated

第四阶段（销毁阶段）：beforeDestroy，destroyed



1）beforeCreate

官网：在实例初始化之后,进行数据侦听和事件/侦听器的配置之前同步调用。

详细：在这个阶段，数据是获取不到的，并且真实dom元素也是没有渲染出来的



2）created

官网：在实例创建完成后被立即同步调用。在这一步中，实例已完成对选项的处理，意味着以下内容已被配置完毕：数据侦听、计算属性、方法、事件/侦听器的回调函数。然而，挂载阶段还没开始，且 $el property 目前尚不可用。

详细：在这个阶段，可以访问到数据了，但是页面当中真实dom节点还是没有渲染出来，在这个钩子函数里面，可以进行相关初始化事件的绑定、发送请求操作



3）beforeMount

官网：在挂载开始之前被调用：相关的 render 函数首次被调用。

详细：代表dom马上就要被渲染出来了，但是却还没有真正的渲染出来，这个钩子函数与created钩子函数用法基本一致，可以进行相关初始化事件的绑定、发送ajax操作



4）mounted

官网：实例被挂载后调用，这时 el 被新创建的 vm.$el 替换了。如果根实例挂载到了一个文档内的元素上，当 mounted 被调用时 vm.$el 也在文档内。 注意 mounted 不会保证所有的子组件也都被挂载完成。如果你希望等到整个视图都渲染完毕再执行某些操作，可以在 mounted 内部使用 vm.$nextTick：

详细：挂载阶段的最后一个钩子函数,数据挂载完毕，真实dom元素也已经渲染完成了,这个钩子函数内部可以做一些实例化相关的操作



5）beforeUpdate

官网：在数据发生改变后，DOM 被更新之前被调用。这里适合在现有 DOM 将要被更新之前访问它，比如移除手动添加的事件监听器。

详细：这个钩子函数初始化的不会执行,当组件挂载完毕的时候，并且当数据改变的时候，才会立马执行,这个钩子函数获取dom的内容是更新之前的内容



6）updated

官网：在数据更改导致的虚拟 DOM 重新渲染和更新完毕之后被调用。 当这个钩子被调用时，组件 DOM 已经更新，所以你现在可以执行依赖于 DOM 的操作。然而在大多数情况下，你应该避免在此期间更改状态。如果要相应状态改变，通常最好使用计算属性或 watcher 取而代之。

详细：这个钩子函数获取dom的内容是更新之后的内容生成新的虚拟dom，新的虚拟dom与之前的虚拟dom进行比对，差异之后，就会进行真实dom渲染。在updated钩子函数里面就可以获取到因diff算法比较差异得出来的真实dom渲染了。



7）beforeDestroy

官网：实例销毁之前调用。在这一步，实例仍然完全可用。

详细：当组件销毁的时候，就会触发这个钩子函数代表销毁之前，可以做一些善后操作,可以清除一些初始化事件、定时器相关的东西。



8）destroyed

官网：实例销毁后调用。该钩子被调用后，对应 Vue 实例的所有指令都被解绑，所有的事件监听器被移除，所有的子实例也都被销毁。

详细：Vue实例失去活性，完全丧失功能



问题：

1）created和mouted

created:在模板渲染成html前调用，即通常初始化某些属性值，然后再渲染成视图。

mounted:在模板渲染成html后调用，通常是初始化页面完成后，再对html的dom节点进行一些需要的操作。



2）computed 和 data

data 和 computed 最核心的区别在于 data 中的属性并不会随赋值变量的改动而改动，而computed 会



### 2、项目结构



![img](http://pcc.huitogo.club/bbad268d08cead7dfc8bf0527f3d4a64)



### 3、数组操作



splice(x，y,z)：在x位置 删除y个元素 再添加z元素进去



... 变量

扩展语法。对数组和对象而言，就是将运算符后面的变量里东西每一项拆下来。



### 4、slot、slot-scope、v-slot



slot用于绑定传入内容的插槽，slot-scope获取插槽的作用域对象

1）slot 占位符 子组件放占用符 父组件填充 分为匿名和具名 ，匿名只有一个

2）slot-scope 传递数据的占位符 子组件放占用符 并绑定数据 父组件使用数据 填充样式



v-slot（2.6版本之后加入）

结合上述两个指令的新指令

1）v-slot:slotName绑定传入的插槽，缩写为#slotName 等价于slot=“slotName”

2）v-slot:slotName=“scope”,获取插槽的作用域对象并赋值给scope,等价于slot-scope=“scope”。同时可以使用ES6的解构语法获取指定的特性v-slot=“{ footer }”

3）当插槽为默认插槽时，v-slot可以不带修饰符，直接在组件上使用，并且将默认插槽的作用域赋给v-slot声明的变量



### 5、$refs 和 ref属性



ref被用来给元素或子组件注册引用信息。引用信息将会注册在父组件的 $refs对象上。如果在普通的 DOM 元素上使用，引用指向的就是 DOM 元素；如果用在子组件上，引用就指向该子组件实例

通俗的讲，ref特性就是为元素或子组件赋予一个ID引用,通过this.$refs.refName来访问元素或子组件的实例。



```
   this.$refs.p
   this.$refs.children
```



this.$refs是一个对象，持有当前组件中注册过 ref特性的所有 DOM 元素和子组件实例

注意： $refs只有在组件渲染完成后才填充，在初始渲染的时候不能访问它们，并且它是非响应式的，因此不能用它在模板中做数据绑定



### 6、.native



.native 可以在某组件的根元素上监听一个原生事件

一般情况下，父组件要监听子组件的事件，可以通过$emit的方式。但是如果父组件要监听子组件的原生事件，比如：input的focus事件。此时可以通过使用v-on的.native修饰符达到目的。



```
<button @click="add(this)">普通的html标签，不包含native的按钮</button>  // 生效
<button @click.native="add(this)">普通的html标签，包含native的按钮</button> // 不生效
<myself-button @click="add(this)"/></myself-button> //不生效
<myself-button @click.native="add(this.id)"/></myself-button>  //生效
```

但是如果目标预监听的元素不是根元素，那么.native可能会失效，此时可以利用emit 的 方·法 ， 通 过 使 用 emit的方法，通过使用emit的方法，通过使用‘listeners来获得父组件在子组件上加上的除.native的事件。 子组件则监听这些事件，当事件发生通知父组件 这个时候就不需要使用.native修饰符就可以监听原生事件的实例。



### 7、scoped



解决多页面应用中不同组件中的样式隔离问题

原理：vue通过在DOM结构以及css样式上加上唯一的标记 data-v-469af010，保证唯一

1）父组件无scoped属性，子组件带有scoped，父组件是无法操作子组件的样式的（原因在原理中可知），虽然我们可以在全局中通过该类标签的标签选择器设置样式，但会影响到其他组件

2）父组件有scoped属性，子组件无，父组件也无法设置子组件样式，因为父组件的所有标签都会带有data-v-469af010唯一标志，但子组件不会带有这个唯一标志属性，与1同理，虽然我们可以在全局中通过该类标签的标签选择器设置样式，但会影响到其他组件

3）父子组建都有，同理也无法设置样式，更改起来增加代码量



副作用



![img](http://pcc.huitogo.club/33061e374b10a760acf5bcb4ef609a6b)



我们自己写的样式却被拼接了这个唯一的标识，我们再怎么操作也是没法命中这个元素的，也就是说Vue并没有给这个input加上这个标识，但是却在我们的样式中加上了这个标识



解决办法：样式穿透



```
<style scoped>

.my-Txt ::v-deep input {
  background-color: pink;
}
</style>
```



![img](http://pcc.huitogo.club/26e2d3b34b739e9a29cb3a34de33e0b0)



可以看到这个唯一标识从input后面跑到了my-Txt的后面了。



### 8、el



简单来说el的作用就是表明我们要将当前vue组件生成的实例插入到页面的哪个元素中，el属性的值可以是css选择器的字符串，或者直接就是对应的元素对象。并且只能在使用new生成实例时才能配置el属性，而我们在组件中只是export一个配置对象，如果设置了el则会报错。



```
new Vue({
  el: '#app',
  router,
  render: h => h(App)
})
```



### 9、$emit 和 $on



组件通信

$emit 触发 $on 监听



### 10、watch 监控事件

观察数据变化

$route：路由事件



### 11、vue-router



this.$router.push()可在组件中控制路由跳转

<router-link/>可在组件模板中设定超链接进行挑战，在Sidebar组件中也已实现

beforeEach 路由鉴权



### 12、v-show与v-if区别



v-show隐藏则是为该元素添加css--display:none，dom元素依旧还在。v-if显示隐藏是将dom元素整个添加或删除



### 13、过渡



动画过渡事件



![img](http://pcc.huitogo.club/e2b8ddea36e76fc9a10cac22c8d79ceb)



钩子函数

```
<transition
  v-on:before-enter="beforeEnter"
  v-on:enter="enter"
  v-on:after-enter="afterEnter"
  v-on:enter-cancelled="enterCancelled"
  v-on:before-leave="beforeLeave"
  v-on:leave="leave"
  v-on:after-leave="afterLeave"
  v-on:leave-cancelled="leaveCancelled"
>
```



### 14、实用的组件



iCheck：基于jQuery的表单选项插件

switchery：把默认的HTML复选框转换成漂亮iOS7样式

daterangepicker：基于bootstrap的日历插件

datatables：jquery表格插件 tooltip（根据需求生成内容和标记）



### 15、实用的模板网站



Gentelella



### 16、export 和 export default



export与export default均可用于导出常量、函数、文件、模块等

在一个文件或模块中，export、import可以有多个，export default仅有一个

通过export方式导出，在导入时要加{ }，export default则不需要，并可以起任意名称



### 17、vuex



本地存储 刷新失效

sessionStorage 会话存储



### 18、Promise



是一个容器（对象），里面是异步事件，用于解决异步回调地狱的问题



### 19、Vue.directive



自定义指令