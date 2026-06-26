from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from web.models.user import UserProfile


# 返回当前登录用户的基本资料。
class GetUserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            user_profile = UserProfile.objects.get(user=user)
            return Response(
                {
                    "result": "success",
                    "user_id": user.id,
                    "username": user.username,
                    "photo": user_profile.photo.url,
                    "profile": user_profile.profile,
                }
            )
        except:
            return Response({"result": "系统异常，请稍后重试"})
