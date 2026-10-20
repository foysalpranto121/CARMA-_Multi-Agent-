from rest_framework import serializers
from .models import RunConfiguration, ExperimentRun, Adaptation, RunResult


class RunConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RunConfiguration
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ExperimentRunSerializer(serializers.ModelSerializer):
    progress_pct   = serializers.FloatField(read_only=True)
    config_code    = serializers.CharField(source='configuration.code', read_only=True)
    config_name    = serializers.CharField(source='configuration.name', read_only=True)
    created_by_name= serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model  = ExperimentRun
        fields = '__all__'
        read_only_fields = [
            'id', 'celery_task_id', 'status', 'total_cases',
            'completed_cases', 'failed_cases', 'started_at',
            'completed_at', 'created_at', 'error_log',
        ]


class ExperimentRunListSerializer(serializers.ModelSerializer):
    progress_pct = serializers.FloatField(read_only=True)
    config_code  = serializers.CharField(source='configuration.code', read_only=True)

    class Meta:
        model  = ExperimentRun
        fields = ['id', 'config_code', 'seed', 'status', 'progress_pct',
                  'total_cases', 'completed_cases', 'started_at', 'created_at']


class AdaptationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Adaptation
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class RunResultSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RunResult
        fields = '__all__'
        read_only_fields = ['id', 'computed_at']
