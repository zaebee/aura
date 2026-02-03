{{/*
Return the Jaeger query URL
*/}}
{{- define "aura.jaeger.queryUrl" -}}
{{- printf "http://aura-jaeger.%s.svc.cluster.local:16686" .Release.Namespace -}}
{{- end -}}

{{/*
Return the Jaeger collector URL
*/}}
{{- define "aura.jaeger.collectorUrl" -}}
{{- printf "http://aura-jaeger.%s.svc.cluster.local:4317" .Release.Namespace -}}
{{- end -}}
