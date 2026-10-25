from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('directory', '0017_copy_anc_links'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='anc',
            name='anc_homepage_link',
        ),
        migrations.RemoveField(
            model_name='anc',
            name='twitter_link',
        ),
    ]
