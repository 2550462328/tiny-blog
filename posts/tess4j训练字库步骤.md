tess4j训练字库步骤
2024-08-22
记录一次tess4j训练字库的步骤
04.jpg
机器学习
huizhang43

使用tess4j做文字识别的时候，如果只用它自带的中文语言包“chi_sim”对中文手写字体或者环境比较复杂的图片，识别正确率不高，因此需要针对特定情况用自己的样本进行训练，提高识别率，通过训练，也可以形成自己的语言库。



怎么训练自己的语言库呢



首先我们需要

1）安装tesseract-ocr 4.0，地址https://digi.bib.uni-mannheim.de/tesseract/

2）下载jTessBoxEditor2.0，地址https://sourceforge.net/projects/vietocr/files/jTessBoxEditor/

3）安装Tess4J-3.4.8 ，地址 [https://sourceforge.net/projects/tess4j/files/tess4j/](https://links.jianshu.com/go?to=https://sourceforge.net/projects/tess4j/files/tess4j/)



接下来，开始



#### **1、准备样本图片**



进行训练的样本图片数量越多越好



#### **2、使用jTessBoxEditor生成训练样本的的合并tif图片**



打开jTessBoxEditor，选择Tools->Merge TIFF，进入训练样本所在文件夹，选中要参与训练的样本图片

点击 “打开” 后弹出保存对话框，选择保存在当前路径下，文件命名为 “zwp.test.exp0.tif” ，格式只有一种 “TIFF” 可选。



tif文面命名格式[lang].[fontname].exp[num].tif

lang是语言，fontname是字体，num为自定义数字。

比如我们要训练自定义字库 zwp，字体名test，那么我们把图片文件命名为 zwp.test.exp0.tif



#### **3、使用tesseract生成.box文件**



执行如下命令 ： tesseract zwp.test.exp0.tif zwp.test.exp0 batch.nochop makebox



#### **4、使用jTessBoxEditor矫正.box文件的错误**



**.box文件记录了每个字符在图片上的位置和识别出的内容，训练前需要使用jTessBoxEditor调整字符的位置和内容。**



打开jTessBoxEditor点击Box Editor ->Open，打开步骤2中生成的“zwp.test.exp0.tif”，会自动关联到“zwp.test.exp0.box”文件，这两文件要求在同一目录下。调整完点击“save”保存修改。



![img](http://pcc.huitogo.club/99e234c2e01bad909923214863dcdf55)



注意这里自定义文字可能是乱码，解决方法： jtessboxeditor的setting ---> Font 里改字体为宋体，regular就可以了。

还需要注意的是修改文字必须是白底黑字，要不然训练时会出现错误



#### **5、生成font_properties文件**



1）执行如下命令： echo test 0 0 0 0 0 >font_properties



2）也可以手工新建一个名为font_properties的文本文件，输入内容 “test 0 0 0 0 0” 表示字体test的粗体、倾斜等共计5个属性。这里的“test”必须与“zwp.test.exp0.box”中的“test”名称一致。



#### **6、使用tesseract生成.tr训练文件**



执行下面命令，执行完之后，会在当前目录生成zwp.test.exp0.tr文件。



tesseract zwp.test.exp0.tif zwp.test.exp0 nobatch box.train



#### **7、生成字符集文件**



执行下面命令：执行完之后会在当前目录生成一个名为“unicharset”的文件。



unicharset_extractor zwp.test.exp0.box



#### **8、生成shape文件**



执行下面命令，执行完之后，会生成 shapetable 和 zwp.unicharset 两个文件。



shapeclustering -F font_properties -U unicharset -O zwp.unicharset zwp.test.exp0.tr



#### **9、生成聚字符特征文件**



执行下面命令，会生成 inttemp、pffmtable、shapetable和zwp.unicharset四个文件。



mftraining -F font_properties -U unicharset -O zwp.unicharset zwp.test.exp0.tr



#### **10、生成字符正常化特征文件**



执行下面命令，会生成 normproto 文件。



cntraining zwp.test.exp0.tr



#### **11、文件重命名**



重新命名inttemp、pffmtable、shapetable和normproto这四个文件的名字为[lang].xxx。



这里修改为zwp.inttemp、zwp.pffmtable、zwp.shapetable和zwp.normproto



执行下面命令：



rename normproto zwp.normproto

rename inttemp zwp.inttemp

rename pffmtable zwp.pffmtable

rename shapetable zwp.shapetable



#### **12、合并训练文件**



执行下面命令，会生成zwp.traineddata文件。



combine_tessdata zwp.



Log输出中的Offset 1、3、4、5、13这些项不是-1，表示新的语言包生成成功。

将生成的“zwp.traineddata”语言包文件复制到Tesseract-OCR 安装目录下的tessdata文件夹中，就可以使用训练生成的语言包进行图像文字识别了。



#### **13、测试**



测试代码如下



```
1. public static void main(String[] args) throws TesseractException { 

2.   //加载待读取图片 

3.   File imageFile = new File("D:\\develop\\tess4J\\img\\1.png"); 

4.   //创建tess对象 

5.   ITesseract instance = new Tesseract(); 

6.   //设置训练文件目录 

7.   instance.setDatapath(System.getProperty("user.dir") + "\\src\\main\\resources\\tessdata"); 

8.   //设置训练语言 

9.   instance.setLanguage("zwp"); 

10.   //执行转换 

11.   String result = instance.doOCR(imageFile); 

12.  

13.   System.out.println(result); 

14. } 
```