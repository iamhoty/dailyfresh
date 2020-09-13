from django.contrib import admin
from django.core.cache import cache
from goods.models import *
# Register your models here.

# admin后台管理
class BaseModelAdmin(admin.ModelAdmin):
    # 当在后台进行数据的更新时,会自动调用admin.ModelAdmin中的save_model方法
    # 所以此时增加更新静态页面index.html的方法
    def save_model(self, request, obj, form, change):
        '''更新表中的数据时调用'''
        # super().save_model(request, obj, form, change)
        super(BaseModelAdmin, self).save_model(request, obj, form, change)

        # 实现网站的页面性能优化的方法
        # 方法1：发出任务,让celery worker 异步 重新生成首页静态页面
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 方法2：清除首页的缓存数据
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        '''删除表中的数据时调用'''
        # super().delete_model(request, obj)
        super(BaseModelAdmin, self).delete_model(request, obj)
        # 发出任务,让celery worker 异步 重新生成首页静态页面
        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 清除首页的缓存数据
        cache.delete('index_page_data')

# 当更新数据时,celery　会执行生成index.html
class GoodsTypeAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass



admin.site.register(GoodsSKU)
admin.site.register(Goods)
admin.site.register(GoodsImage)

admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)
