from rest_framework import serializers
from .models import EventLog, Case, BenchmarkScenario, BenchmarkCase, GoldAnnotation


class EventLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = EventLog
        fields = '__all__'
        read_only_fields = ['id', 'imported_at']


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Case
        fields = '__all__'
        read_only_fields = ['id']


class BenchmarkScenarioSerializer(serializers.ModelSerializer):
    case_count = serializers.SerializerMethodField()

    class Meta:
        model  = BenchmarkScenario
        fields = '__all__'

    def get_case_count(self, obj):
        return obj.benchmark_cases.count()


class BenchmarkCaseSerializer(serializers.ModelSerializer):
    scenario_code = serializers.CharField(source='scenario.code', read_only=True)
    case_id_str   = serializers.CharField(source='case.case_id', read_only=True)

    class Meta:
        model  = BenchmarkCase
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class GoldAnnotationSerializer(serializers.ModelSerializer):
    annotator_name = serializers.CharField(source='annotator.get_full_name', read_only=True)

    class Meta:
        model  = GoldAnnotation
        fields = ['id', 'benchmark_case', 'annotator', 'annotator_name', 'strategy',
                  'activity_seq', 'agrees_with_reference', 'notes',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'benchmark_case', 'annotator', 'created_at', 'updated_at']

    def validate_activity_seq(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError('A list of activity names is expected.')
        return value


class BenchmarkCaseListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer (no heavy JSON fields)."""
    scenario_code = serializers.CharField(source='scenario.code', read_only=True)
    case_id_str   = serializers.CharField(source='case.case_id', read_only=True)

    class Meta:
        model  = BenchmarkCase
        fields = ['id', 'scenario_code', 'case', 'case_id_str', 'is_validated',
                  'gold_viol_cost', 'gold_exec_cost', 'kappa',
                  'annotator_1', 'annotator_2', 'created_at']
