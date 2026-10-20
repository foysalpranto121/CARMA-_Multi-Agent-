from rest_framework import serializers
from .models import Process, ConstraintSet, Constraint, CorpusDocument


class ConstraintSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Constraint
        fields = '__all__'


class ConstraintSetSerializer(serializers.ModelSerializer):
    constraints = ConstraintSerializer(many=True, read_only=True)

    class Meta:
        model  = ConstraintSet
        fields = '__all__'


class ProcessSerializer(serializers.ModelSerializer):
    created_by_name  = serializers.SerializerMethodField()
    constraint_count = serializers.SerializerMethodField()

    class Meta:
        model  = Process
        fields = '__all__'
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def get_constraint_count(self, obj):
        return obj.constraint_sets.filter(is_active=True).count()


class CorpusDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CorpusDocument
        fields = '__all__'
        read_only_fields = ['id', 'qdrant_id', 'created_at']
