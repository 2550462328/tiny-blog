# encoding: utf-8
# author:yangyongzhen
# blog.csdn.net/qq8864
from flask import Flask, render_template, request, redirect
import statistic
import articles
import atexit
import json
import os

app = Flask(__name__, template_folder="templates", static_folder="static", static_url_path="/static")

# 访问安全认证码
verify_code = "111111"


# 首页
@app.route('/')
def index():
    statistic.Stat.totalVisit += 1
    print(statistic.Stat.ntce)
    page = 1
    page = request.args.get('page', 1, int)
    print(page)
    nums = len(articles.AllArts)
    print(nums)
    allpage = int(nums / 5)
    if nums % 5 != 0:
        allpage = int(nums / 5) + 1
    # print(allpage)

    curArts = articles.AllArts
    if (page * 5) < nums:
        curArts = articles.AllArts[(page - 1) * 5: page * 5]
    else:
        curArts = articles.AllArts[(page - 1) * 5: nums]
    # 分页表
    tabs = []
    for i in range(0, allpage):
        tabs.append(i)
    print(tabs)
    return render_template("index.html", arts=curArts, news=articles.NewArts[:9], hots=articles.HotArts[:9],
                           notice=statistic.Stat.ntce, items=articles.ItemList, curPage=page, tab=tabs)  # 加入变量传递


@app.route('/about')
def about():
    msg = "my name is caojianhua, China up!"
    return render_template("about.html", data=msg)  # 加入变量传递


# 分类页
@app.route('/items')
def items():
    try:
        id = request.args.get('id')
        print(id)
        allArts = []
        allMaps = articles.ItemMap[id]
        # 遍历 hash
        for v in allMaps.values():
            allArts.append(v)
            # 按日期排序
        allArts.sort(key=lambda x: x['date'], reverse=True)
        # print(allArts)
        page = 1
        page = request.args.get('page', 1, int)
        print(page)
        nums = len(allArts)
        print(nums)
        allpage = int(nums / 5)
        if nums % 5 != 0:
            allpage = int(nums / 5) + 1
        print(allpage)
        curArts = allArts
        if (page * 5) < nums:
            curArts = allArts[(page - 1) * 5: page * 5]
        else:
            curArts = allArts[(page - 1) * 5: nums]
        # 分页表
        tabs = []
        for i in range(0, allpage):
            # print(i)
            tabs.append(i)
        # print(tabs)
        return render_template("items.html", arts=curArts, item=id, items=articles.ItemList, news=articles.NewArts[:9],
                               hots=articles.HotArts[:9], curPage=page, tab=tabs)
    except Exception as e:
        print("Exception occured")
        print(e)
        return render_template('404.html')


# 文章详情页
@app.route('/article_detail')
def article_detail():
    try:
        id = request.args.get('id')
        # print(id)
        # 取出分类
        item = articles.ArtRouteMap[id]['item']
        print(item)
        art = articles.ItemMap[item][id]
        # art_index  = NewPosts.index(id)
        # 遍历获取文章上一篇和下一篇的文章
        pre_art = art
        next_art = art
        art_list = list(articles.ItemMap[item].values())
        length = len(art_list)
        for i in range(length):
            if art_list[i]['id'] == id:
                break

        if i != 0:
            pre_art = art_list[i - 1]
        if i != length - 1:
            next_art = art_list[i + 1]

        statistic.Stat.artStat[id]['visitCnt'] += 1
        statistic.Stat.totalVisit += 1
        articles.ItemMap[item][id]['visitCnt'] = statistic.Stat.artStat[id]['visitCnt']
        # print(art)
        # print(item_index)
        # print(art_index)
        return render_template("article_detail.html", data=art, pre=pre_art, next=next_art, items=articles.ItemList,
                               news=articles.NewArts[:9], hots=articles.HotArts[:9])
    except Exception as e:
        print("Exception occured")
        return render_template('404.html')


# 说说页面  
@app.route('/moodList')
def moodList():
    msg = "my name is caojianhua, China up!"
    return render_template("moodList.html", data=msg)


# 留言页面 
@app.route('/comment')
def comment():
    msg = "my name is caojianhua, China up!"
    return render_template("comment.html", data=msg)


# admin页面 
@app.route('/admin')
def admin():
    return render_template("admin.html")


# 提交说说
@app.route('/saysay', methods=['POST', 'GET'])
def saysay():
    my_notice = {'TimeOut': 5, 'Href': '/', 'IsSucc': True, 'Mess': '成功'}
    print(request.form)
    code = request.form['code']
    if code != verify_code:
        my_notice['IsSucc'] = False
        my_notice['Mess'] = '授权码错误'
    else:
        my_notice['IsSucc'] = True

    print(my_notice)
    return render_template("success.html", nt=my_notice)


# 提交公告
@app.route('/pub_notice', methods=['POST', 'GET'])
def pub_notice():
    my_notice = {'TimeOut': 5, 'Href': '/', 'IsSucc': True, 'Mess': '成功'}
    print(request.form)
    code = request.form['code']
    if code != verify_code:
        my_notice['IsSucc'] = False
        my_notice['Mess'] = '授权码错误'
    else:
        my_notice['IsSucc'] = True
        statistic.Stat.ntce = request.form['notice']
    return render_template("success.html", nt=my_notice)


# 提交置顶
@app.route('/pub_top', methods=['POST', 'GET'])
def pub_top():
    my_notice = {'TimeOut': 5, 'Href': '/', 'IsSucc': True, 'Mess': '成功'}
    print(request.form)
    code = request.form['code']
    if code != verify_code:
        my_notice['IsSucc'] = False
        my_notice['Mess'] = '授权码错误'
    else:
        my_notice['IsSucc'] = True
        statistic.Stat.top_art = request.form['top']
    return render_template("success.html", nt=my_notice)


# 文件上传(发布文章)
@app.route('/file_upload', methods=['POST', 'GET'])
def file_upload():
    print(request.files)
    my_notice = {'TimeOut': 5, 'Href': '/', 'IsSucc': True, 'Mess': '成功'}
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        print(file)
        code = request.form['code']
        if code != verify_code:
            my_notice['IsSucc'] = False
            my_notice['Mess'] = '授权码错误'
        else:
            my_notice['IsSucc'] = True
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], file.filename))
            print(file.filename)
            articles.getPosts()
    else:
        return render_template('404.html')

    return render_template("success.html", nt=my_notice)


@app.route('/404')
def error_404():
    print("error_404")
    return render_template("404.html")


@app.errorhandler(404)
def page_not_found(e):
    print("page_not_found")
    print(e)
    return render_template('404.html'), 404


@app.errorhandler(Exception)
def handle_exception(e):
    # 捕获其他异常
    print("handle_exception")
    print(e)
    return render_template('404.html'), 500


def saveData():
    # 保存访问量数据
    with open('statistic.json1', 'w', encoding='utf-8') as f:
        json.dump(statistic.Stat.__dict__, f, ensure_ascii=False)


# 监控退出时保存统计信息
@atexit.register
def exit_handler():
    print("应用程序退出")
    saveData()


if __name__ == "__main__":
    # 启动时加载访问量数据
    articles.getPosts()
    app.config['UPLOAD_FOLDER'] = 'posts'
    app.run(port=8000, host="0.0.0.0", debug=False)
    print("over")
