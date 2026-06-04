from rest_framework import serializers
from .models import Rezept


class RezeptSerializer(serializers.ModelSerializer):

    class Meta:
        model  = Rezept
        fields = '__all__'
        read_only_fields = ['user', 'erstellt', 'geaendert']
