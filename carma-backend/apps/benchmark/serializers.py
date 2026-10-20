from rest_framework import serializers
from .models import EventLog, Case, BenchmarkScenario, BenchmarkCase


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


class BenchmarkCaseListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer (no heavy JSON fields)."""
    scenario_code = serializers.CharField(source='scenario.code', read_only=True)

    class Meta:
        model  = BenchmarkCase
        fields = ['id', 'scenario_code', 'case', 'is_validated',
                  'gold_viol_cost', 'gold_exec_cost', 'kappa', 'created_at']
