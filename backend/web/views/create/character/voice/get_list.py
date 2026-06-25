from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from web.models.character import Voice


# 返回所有可选音色列表（id + 名称）。
class GetVoiceList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            voices_raw = Voice.objects.order_by('id')
            voices = []
            for v in voices_raw:
                voices.append({
                    'id': v.id,
                    'name': v.name,
                })
            return Response({
                'result': 'success',
                'voices': voices,
            })
        except:
            return Response({
                'result': '系统异常，请稍后重试'
            })
