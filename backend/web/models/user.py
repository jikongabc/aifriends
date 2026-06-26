import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils.timezone import now, localtime


# 生成用户头像的随机上传路径，避免文件名冲突。
def photo_upload_to(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4().hex[:10]}.{ext}"
    return f"user/photos/{instance.user_id}_{filename}"


# 用户扩展资料：一对一关联 Django User，存头像与简介。
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    photo = models.ImageField(
        default="user/photos/default.png", upload_to=photo_upload_to
    )
    profile = models.TextField(default="谢谢你的关注", max_length=500)
    create_time = models.DateTimeField(default=now)
    update_time = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.user.username} - {localtime(self.create_time).strftime('%Y-%m-%d %H:%M:%S')}"
