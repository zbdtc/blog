#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'z b'

' url handlers '

import re, time, json, logging, hashlib, base64, asyncio
from coroweb import get, post
from Models import User, Comment, Blog, next_id
from config import configs
from aiohttp import web
from apis import Page, APIValueError, APIResourceNotFoundError, APIError

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


#--------------------------------------------------------------------------------------
#检测当前用户是否是管理员
def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPremissionError()

# 根据用户信息拼接一个cookie字符串
def user2cookie(user, max_age):
    # build cookie string by: id-expires-sha1
    # 过期时间是当前时间+设置的有效时间
    expires = str(int(time.time() + max_age))
    # 构建cookie存储的信息字符串
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    # 用-隔开，返回
    return '-'.join(L)

# 根据cookie字符串，解析出用户信息相关的
async def cookie2user(cookie_str):
    # cookie_str是空则返回
    if not cookie_str:
        return None
    try:
        # 通过'-'分割字符串
        L = cookie_str.split('-')
        # 如果不是3个元素的话，与我们当初构造sha1字符串时不符，返回None
        if len(L) != 3:
            return None
        # 分别获取到用户id，过期时间和sha1字符串
        uid, expires, sha1 = L
        # 如果超时，返回None
        if int(expires) < time.time():
            return None
        # 根据用户id查找库，对比有没有该用户
        user = await User.find(uid)
        # 没有该用户返回None
        if user is None:
            return None
        # 根据查到的user的数据构造一个校验sha1字符串
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        # 比较cookie里的sha1和校验sha1，一样的话，说明当前请求的用户是合法的
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        # 返回合法的user
        return user
    except Exception as e:
        logging.exception(e)
        return None

# 获取页数，主要是做一些容错处理
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p
#-----------------------------------------------------------------

#首页
@get('/')
def home(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }

#注册页
@get('/register')
def register(request):
    print('type of request= ------------',type(request))
    print(request)
    print(request.items())
    # print(type(request['request']))
    # print(dir(request['request']))
    print(request.json)
    return{
        '__template__' : 'register.html'
    }


#注册请求处理
@post('/api/users')
async def api_register_user(*, email, name, passwd):
    # print('type of request= ------------',type(request))
    # print(request)
    # print(request.items())
    # print(type(request['request']))
    # print(dir(request['request']))
    # print(request['request'].json)
    print(email, name, passwd)

    # 判断name是否存在，且是否只是'\n', '\r',  '\t',  ' '，这种特殊字符
    if not name or not name.strip():
        raise APIValueError('name')
    # 判断email是否存在，且是否符合规定的正则表达式
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    # 判断passwd是否存在，且是否符合规定的正则表达式
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')

    #检测数据库中是否有相同的email地址，如果有，提示用户email已被注册
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIValueError('register:failed', 'email', 'Email is already in use.')

    #生产注册用户唯一uid
    uid = next_id()
    #构建sha1_passwd
    sha1_passwd = '%s:%s' % (uid,passwd)

    admin = False
    if email == 'admin@163.com':
        admin = True

    #创建用户
    user = User(
        id=uid,
        name=name.strip(),
        email=email,
        #密码存储用sha1算法转化
        passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), 
        #存储头像图床地址
        image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest(), 
        admin=admin
        )
    await user.save()
    logging.info('save user ok')

    r = web.Response()
    #添加cookie
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    #把返回的实例的密码改成‘**************’，防止密码泄露
    user.passwd = '*******'
    #返回的shijson，所及设置content-type为json
    r.content_type = 'application/json'
    #把对象转换成json格式
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r

#登录页面
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }


#登录请求处理
@post('/api/authenticate')
async def authenticate(*, email, passwd):
    # 如果email或passwd为空，都说明有错误
    if not email:
        raise APIValueError('email', 'Invalid email')
    if not passwd:
        raise APIValueError('passwd', 'Invalid  passwd')
    # 根据email在库里查找匹配的用户
    users = await User.findAll('email=?', [email])
    # 没找到用户，返回用户不存在
    if len(users) == 0:
        raise APIValueError('email', 'email not exist')
    # 取第一个查到用户，理论上就一个
    user = users[0]
    # 按存储密码的方式获取出请求传入的密码字段的sha1值
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    # 和库里的密码字段的值作比较，一样的话认证成功，不一样的话，认证失败
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid passwd')
    # 构建返回信息
    r = web.Response()
    # 添加cookie
    r.set_cookie(COOKIE_NAME, user2cookie(
        user, 86400), max_age=86400, httponly=True)
    # 只把要返回的实例的密码改成'******'，库里的密码依然是正确的，以保证真实的密码不会因返回而暴漏
    user.passwd = '******'
    # 返回的是json数据，所以设置content-type为json的
    r.content_type = 'application/json'
    # 把对象转换成json格式返回
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#登出请求
@get('/api/signout')
def signout(request):
    referer = request.headers.get('referer')
    r = web.HTTPFound(referer or '/')
    print('httpfound------------', type(r))
    print(dir(r))
    print(r.status_code)
    r.set_cookie(COOKIE_NAME, '-deleted', max_age=0, httponly=True)
    logging.info('user signed out')
    return r

#----------------------------博客管理----------------

#博客创建页面
@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'  # 对应HTML页面中VUE的action名字
    }


#API保存博客
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
    # 只有管理员可以写博客
    check_admin(request)
    # name，summary,content 不能为空
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty')

    # 根据传入的信息，构建一条博客数据
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name,
                user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    # 保存
    await blog.save()
    return blog

#博客管理页面
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
}

# API获取博客信息
@get('/api/blogs')
async def api_blogs(*, page='1'):
    print('page=========', page)
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(num, page_index, 5)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)

#博客修改页面
@get('/manage/blogs/modify/{id}')
def manage_modify_blog(id):
    print('start----------------manage_modify_blog(id)')
    return {
        '__template__': 'manage_blog_modify.html',
        'id': id,
        'action': '/api/blogs/modify'
        }


# API获取某条博客的信息
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog


# API保存对某条博客的修改
@post('/api/blogs/modify')
async def api_modify_blog(request, *, id, name, summary, content):
    logging.info("修改的博客的博客ID为：%s", id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty')   

    blog = await Blog.find(id)
    blog.name = name
    blog.summary = summary
    blog.content = content
    await blog.update()
    return blog


# 根据博客id查询该博客信息
@get('/blog/{id}')
async def get_blog(request,*,id):
    blog = await Blog.find(id)
    # 根据博客id查询该条博客的评论
    # comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    # # markdown2是个扩展模块，这里把博客正文和评论套入到markdonw2中
    # for c in comments:
    #     c.html_content = text2html(c.content)
    # blog.html_content = markdown2.markdown(blog.content)
    # 返回页面
    return {
        '__template__': 'blog.html',
        'blog': blog,
        # 'comments': comments,
    }

# 删除一条博客
@post('/api/blogs/{id}/delete')
async def api_delete_blog(id, request):
    logging.info("删除博客的博客ID为：%s" % id)
    # 先检查是否是管理员操作，只有管理员才有删除评论权限
    check_admin(request)
    # 查询一下评论id是否有对应的评论
    b = await Blog.find(id)
    # 没有的话抛出错误
    if b is None:
        raise APIResourceNotFoundError('Comment')
    # 有的话删除
    await b.remove()
    return dict(id=id)

#------------------用户管理-----------------------------------
# 显示所有的用户
@get('/show_all_users')
async def show_all_users():
    users = await User.findAll()
    logging.info('to index...')
    # return (404, 'not found')

    return {
        '__template__': 'users.html',
        'users': users
    }

@get('/api/users')
async def aip_get_users(*, page=1):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index, 5)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    logging.info('users = %s and type = %s' % (users, type(users)))
    for u in users:
        u.passwd = '******'
    return dict(users=users,page=p)

# 查看所有用户
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

#--------------------评论管理------------------------------
#发表评论
@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    # 对某个博客发表评论
    user = request.__user__
    # 必须为登陆状态下，评论
    if user is None:
        raise APIPermissionError('content')
    # 评论不能为空
    if not content or not content.strip():
        raise APIValueError('content')
    # 查询一下博客id是否有对应的博客
    blog = await Blog.find(id)
    # 没有的话抛出错误
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    # 构建一条评论数据
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name,
                      user_image=user.image, content=content.strip())
    # 保存到评论表里
    await comment.save()
    return comment

#获取评论
@get('/api/{id}/comments')
async def api_comments(request, *, id):
    comment = await Comment.findAll('blog_id=\''+id+'\'', orderBy='created_at desc')
    print(comment)
    return {
        'comments':comment
    }




















@get('/a')
async def a(request):
    body = '<h1>hello:/greeting xxxx<h1>' 
    return body



@post('/api/test')
def x(request):
    print('type of request= ------------',type(request))
    print(request)
    print(request.items())
    print(type(request['request']))
    print(dir(request['request']))
    print(request['request'].json)













@get('/ajax')
async def ajax_test(request):
    return {
        '__template__' : 'Ajax.html'
    }