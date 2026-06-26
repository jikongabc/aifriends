from django.shortcuts import render


# 返回前端 SPA 入口页。
def index(request):
    return render(request, "index.html")
