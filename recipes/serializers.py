from rest_framework import serializers
from .models import Rezept, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tag
        fields = ['id', 'name']


class RezeptSerializer(serializers.ModelSerializer):
    tags_detail = TagSerializer(source='tags', many=True, read_only=True)

    class Meta:
        model  = Rezept
        fields = '__all__'
        read_only_fields = ['user', 'erstellt', 'geaendert']
