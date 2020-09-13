# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0003_auto_20190116_1604'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderinfo',
            name='trade_no',
            field=models.CharField(max_length=128, default='', verbose_name='支付编号'),
        ),
    ]
