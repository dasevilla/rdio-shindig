# Generated by Django 3.0.4 on 2020-04-10 23:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sutrofm', '0002_auto_20200410_2239'),
    ]

    operations = [
        migrations.AlterField(
            model_name='party',
            name='name',
            field=models.CharField(db_index=True, max_length=128),
        ),
    ]
