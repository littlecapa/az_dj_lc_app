from rest_framework import serializers
from .models import Rezept, Tag


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tag
        fields = ['id', 'name']


class RezeptSerializer(serializers.ModelSerializer):
    tags_detail = TagSerializer(source='tags', many=True, read_only=True)
    # Freitexteingabe: "vegan; schnell; Sommer" → Tags per get_or_create
    tags_input  = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default=''
    )

    class Meta:
        model  = Rezept
        fields = '__all__'
        read_only_fields = ['user', 'erstellt', 'geaendert', 'tags']

    def _parse_tags(self, tags_input):
        """Semikolon-getrennte Tag-Namen → Tag-Objekte (neu anlegen falls nötig)."""
        tags = []
        for name in tags_input.split(';'):
            name = name.strip()
            if name:
                tag, _ = Tag.objects.get_or_create(name=name)
                tags.append(tag)
        return tags

    def create(self, validated_data):
        tags_input = validated_data.pop('tags_input', '')
        instance   = super().create(validated_data)
        instance.tags.set(self._parse_tags(tags_input))
        return instance

    def update(self, instance, validated_data):
        tags_input = validated_data.pop('tags_input', None)
        instance   = super().update(instance, validated_data)
        if tags_input is not None:
            instance.tags.set(self._parse_tags(tags_input))
        return instance
