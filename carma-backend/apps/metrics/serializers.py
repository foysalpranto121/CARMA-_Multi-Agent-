from rest_framework import serializers
from .models import RunMetrics

class RunMetricsSerializer(serializers.ModelSerializer):
    config_code = serializers.CharField(source='run.configuration.code', read_only=True)
    class Meta:
        model  = RunMetrics
        fields = '__all__'
        read_only_fields = ['id', 'computed_at']
