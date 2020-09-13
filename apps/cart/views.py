import json

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django_redis import get_redis_connection
from goods.models import GoodsSKU
# Create your views here.
# 添加商品到购物车:
# 1）请求方式，采用ajax post
# 如果涉及到数据的修改(新增，更新，删除), 采用post
# 如果只涉及到数据的获取，采用get
# 2) 传递参数: 商品id(sku_id) 商品数量(count)
# 3) 返回给前端的数据是什么,数据格式是什么


from django.views.generic import View
from utils.mixin import LoginRequiredMixin

# ajax发起的请求都在后台，在浏览器中看不到效果
# 所以不能用utils中的mixin中的LoginRequiredMixin来判断用户是否登录
# 因为用户没有登录时,页面是不会跳转到登录页面的
# /cart/add
class CartAddView(View):
    '''购物车记录添加'''
    def post(self,request):
        '''购物车记录添加'''
        # 判断用户是否登录,只有登录了才能添加购物车
        # 用户登录user为User的实例对象，user.is_authenticated()返回为真
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            # dic = json.dumps({'res':0,'errmsg':"请先登录"})
            # return HttpResponse(dic)
            return JsonResponse({'res':0,'errmsg':"请先登录"})

        # 接收数据 post请求不会显示在地址栏处
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 数据完整性校验
        if not all([sku_id,count]):
            dic = json.dumps({'res': 1, 'errmsg': "数据不完整"})
            return HttpResponse(dic)
            # return JsonResponse({'res': 1, 'errmsg': "数据不完整"})

        # 校验添加的商品数量
        try:
            count = int(count)
        except Exception as e:
            # 数目出错
            dic = json.dumps({'res': 2, 'errmsg': "商品数目出错"})
            return HttpResponse(dic)
            # return JsonResponse({'res': 2, 'errmsg': "商品数目出错"})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            dic = json.dumps({'res': 3, 'errmsg': "商品不存在"})
            return HttpResponse(dic)
            # return JsonResponse({'res': 3, 'errmsg': "商品不存在"})

        # 先查看购物车是否有商品
        # 业务处理:添加购物车记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 先尝试获取sku_id的值 -> hget cart_key 属性
        # 如果sku_id在hash中不存在,hget返回None
        car_count = conn.hget(cart_key,sku_id)
        if car_count:
            # 累加购物车中商品的数目
            count += int(car_count)

        # 校验商品的库存
        if count > sku.stock:
            # 商品库存不足
            dic = json.dumps({'res': 4, 'errmsg': "商品库存不足"})
            return HttpResponse(dic)
            # return JsonResponse({'res': 3, 'errmsg': "商品库存不足"})

        # 设置hash中sku_id对应的值
        # hset->如果sku_id已经存在，更新数据， 如果sku_id不存在，添加数据
        conn.hset(cart_key,sku_id,count)

        # 计算用户购物车商品的条目数
        total_count = conn.hlen(cart_key)

        # 返回应答
        dic = json.dumps({'res': 5, 'total_count':total_count,'message': "添加成功!"})
        return HttpResponse(dic)
        # return JsonResponse({'res': 3, 'errmsg': "商品库存不足"})

# /cart
# 因为没有涉及到ajax 所以可用到LoginRequiredMixin
class CartInfoView(LoginRequiredMixin,View):
    '''购物车页面显示'''
    def get(self,request):
        # 获取登录的用户
        user = request.user
        # 获取用户购物车中的商品信息
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        # 得到的是python字典 {'商品id':商品数量, '商品id':商品数量,...}
        cart_dict = conn.hgetall(cart_key)

        # 存储不同类型的商品
        skus = []
        # 保存用户购物车中商品的总数目和总价格
        total_count = 0
        total_price = 0
        # 遍历获取商品的信息 items得到是字典的 键：值
        for sku_id,count in cart_dict.items():
            # 根据商品的id获取商品的信息
            sku = GoodsSKU.objects.get(id=sku_id)
            # 计算商品的小计 count遍历出来是字符串需要进行转换
            # todo 保存2位小数
            amount = sku.price * int(count)

            # 动态给sku对象增加一个属性amount, 保存商品的小计
            sku.amount = amount
            # 动态给sku对象增加一个属性count, 保存购物车中对应商品的数量
            sku.count = count
            # 添加
            skus.append(sku)

            # 累加计算商品的总数目和总价格
            total_count += int(count)
            total_price += amount

        # 组织上下文
        # context = {'total_count': total_count,
        #            'total_price': total_price,
        #            'skus': skus}

        # 使用模板
        return render(request,'cart.html',locals())


# 更新购物车记录
# 采用ajax post请求
# 前端需要传递的参数:商品id(sku_id) 更新的商品数量(count)
# /cart/update
class CartUpdateView(View):
    '''购物车记录更新'''
    def post(self,request):
        '''购物车记录更新'''
        # 判断用户是否登录
        user = request.user
        if not user.is_authenticated():
            # 用户未登录
            return JsonResponse({"res":0,"errmsg":"请先登录!"})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')
        # 数据校验
        if not all([sku_id,count]):
            return JsonResponse({"res":1,"errmsg":"数据不完整"})

        # 校验添加的商品数量
        try:
            count = int(count)
        except Exception as e:
            # 商品数目错误
            return JsonResponse({"res":2,"errmsg":"商品数目错误"})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({"res":3,"errmsg":"商品不存在"})

        # 业务处理:更新购物车记录
        conn = get_redis_connection('default')
        cart_key = 'card_%d' % user.id

        # 校验商品的库存
        if count > sku.stock:
            return JsonResponse({"res":4,"errmsg":'商品库存不足'})

        # 更新
        conn.hset(cart_key,sku_id,count)

        # 计算用户购物车中商品的总件数  从redis中获取购物车中所有的商品id 并进行遍历{'1':5,'2':3}
        # 总件数不会因为选中与没选中而发生变化,记录的是购物车中所有的商品数量
        total_count = 0
        # 获取所有键的值 返回的是列表
        vals = conn.hvals(cart_key) # 该购物车中所有商品的数量
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({"res":5,"total_count":total_count,'message':"更新成功"})

# 删除购物车的记录
# 采用ajax psot
# 前端需要传递过来的参数是： 只有商品的id(sku_id)
# /cart/delete
class CartDeleteView(View):
    '''购物车记录删除'''
    def post(self,request):
        '''购物车记录删除'''
        # 判断用户是否登录
        user = request.user
        if  not user.is_authenticated():
            return JsonResponse({"res":0,"errmsg":"请先登录"})

        # 接受参数
        sku_id = request.POST.get('sku_id')

        # 数据校验
        if not sku_id:
            return JsonResponse({"res":1,"errmsg":"无效的商品id"})

        # 判断该id的商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            # 商品不存在
            return JsonResponse({"res":2,"errmsg":'商品不存在'})

        # 业务处理 删除购物车的记录
        # 获得redis的连接拼接出cart_key
        conn = get_redis_connection('default')
        cart_key = "cart_%d" % user.id

        # 删除购物车的这个商品 hdel(name,key*) 购物车id　商品id
        conn.hdel(cart_key,sku_id) # 同步到redis数据库中

        # 计算用户购物车中商品的总件数  从redis中获取购物车中所有的商品id 并进行遍历{'1':5,'2':3}
        # 总件数不会因为选中与没选中而发生变化,记录的是购物车中所有的商品数量
        total_count = 0
        # 获取所有键的值 返回的是列表
        # 该购物车中所有商品的数量
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        # 返回应答
        return JsonResponse({"res":3,'total_count':total_count,"message":"删除成功"})
















































