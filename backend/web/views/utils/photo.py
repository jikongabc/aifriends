import os

from django.conf import settings


# 删除旧头像文件（默认头像除外），避免上传新图后残留垃圾文件。
def remove_old_photo(photo):
    if photo and photo.name != "user/photos/default.png":
        old_path = settings.MEDIA_ROOT / photo.name
        if os.path.exists(old_path):
            os.remove(old_path)
