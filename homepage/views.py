from django.shortcuts import render
from django.http import HttpResponse

def index(request):
    return HttpResponse("Hallo! Das ist die neue Homepage App auf Azure. 🚀")
