# How to Install Cloud Service Mesh on Cloud Run

### Overview

When deploying a mesh resource for Cloud Run services, we need to identify which service is a _caller_ or a _destination_. 

* **Caller** - Any service that sends requests to other Cloud Run services, thus invoking them.
* __Destination__ - Any service that does not initiate a request to other Cloud Run services. They could respond back to other services or make API calls to other GCP products but they do not invoke other Cloud Run services themselves.

This is important to understand as _destination_ services as (explain why they don't need to be registered in the mesh). Instead these services need:
- A serverless NEG (or network endpoint group) and an internal backend service that points at the NEG.
- One or more HTTPRoute objects that map a hostname to those backend services.
## Prerequisites

1. Enable the necessary APIs (if you haven't done so already)

```bash
gcloud services enable \
	networkservices.googleapis.com \
	trafficdirector.googleapis.com \
	dns.googleapis.com \
	run.googleapis.com
```

2. Assign the necessary permissions to each service account used in Cloud Run. It is a best practice for each service to have its own SA.

```bash
# Allow public facing agent to invoke other downstream agents
gcloud run services add-iam-policy-binding $AGENT_NAME \
	--region=$REGION \
	--member=serviceAccount:srkw-regulator@$PROJECT_ID.iam.gserviceaccount.com \
	--role=roles/run.invoker
	
# Another option is to grant the invoker role to the Traffic Director client SA
gcloud run services add-iam-policy-binding $AGENT_NAME \
	--region=$REGION \
	--member=serviceAccount:$PROJECT_NUM-compute@developer.gserviceaccount.com \
	--role=roles/run.invoker 
```

Repeat this procedure for all downstream agents. This is the simplest and most reliable way to ensure services don't invoke other services unless desired.

> __Why are we doing this?__
> You may be thinking that there's no reason to restrict communication via IAM roles but this is a best practice to ensure security regardless of networking methods implemented. Think of IAM permissions as the bridge that permits one service to call another while the mesh functions as the guard at each bridge checking who can cross over.

## Deploy the necessary resources

1. Creating the mesh resource is pretty easy, just create a `mesh.yaml` file and enter the desired name as a field.

```bash
cat > mesh.yaml << 'EOF'
name: srkw-mesh
EOF

gcloud network-services meshes import srkw-mesh \
	--source=mesh.yaml \
	--location=global
```

2. Set up DNS for mesh hostnames. There are two ways of doing this {dive deeper later}
 but we're going with option A as it is the quickest.

```bash
# Private zone for the mesh domain
gcloud dns managed-zones create srkw-mesh \
	--description="Domain for svc.mesh.private" \
	--dns-name=svc.mesh.private. \
	--networks=$VPC_NAME \
	--visibility=private
	
# Wildcard A record pointing to any RFC1918
gcloud dns record-sets create "*.svc.mesh.private." \
	--type=A \
	--zone="srkw-mesh" \
	--rrdatas=10.0.0.1 \
	--ttl=3600
```

3. Deploy the cloud run services, if not done already. For each one, create a serverless NEG and backendService

```bash
gcloud compute network-endpoint-groups create "${AGENT_NAME}-neg" \
	--region=$REGION \
	--network-endpoint-type=serverless \
	--cloud-run-service=$AGENT_NAME
	
gcloud compute backend-services create "${AGENT_NAME}-region" \
	--global \
	--load-balancing-scheme=INTERNAL_SELF_MANAGED

gcloud compute backend-services add-backend "${AGENT_NAME}-region" \
	--global \
	--network-endpoint-group="${AGENT_NAME}-neg" \
	--network-endpoint-group-region=$REGION
```

4. Create the HTTPRoutes

We'll create two kinds of routes:
- Direct routes for agents B and C - each one will have a stable hostname under the private DNS zone to allow A to call them directly

```bash
cat > llm-proxy-route.yaml << 'EOF'
name: 'llm-proxy-route'
hostnames: 
- "llm.svc.mesh.private"
meshes:
- "projects/${PROJECT_ID}/locations/global/backendServices/biologist-agent-v1-region"
EOF

cat > vessel-route.yaml << 'EOF'
name: 'vessel-route'
hostnames: 
- "vessel.svc.mesh.private"
meshes:
- "projects/multi-agent-run-demo/locations/global/backendServices/vessel-agent-region"
EOF

gcloud network-services http-routes import llm-proxy-region \
	--source=llm-proxy-route.yaml \
	--location=global
	
gcloud network-services http-routes import vessel-agent-region \
	--source=vessel-route.yaml \
	--location=global
```

- Weighed route for B + D (80/20) split - expose a single logical hostname and split across two backend services
```bash
cat > biologist-split-route.yaml << 'EOF'
name: "biologist-split-route"
hostnames:
- "biologist-agent.svc.mesh.private"
meshes:
- "projects/multi-agent-run-demo/locations/global/meshes/srkw-mesh"
rules:
- action:
	destinations:
	- serviceName: "projects/multi-agent-run-demo/locations/global/backendServices/biologist-agent-v1-region"
	  weight: 80
	- serviceName: "projects/multi-agent-run-demo/locations/global/backendServices/biologist-agent-v2-region"
	  weight: 20
EOF

gcloud network-services http-routes import biologist-split-route \
	--source=biologist-split-route.yaml \
	--location=global
```

## Install the mesh

1. Begin by deploying service __A__ as a mesh client

```bash
placeholder
```

## Test the mesh

```bash
export REGULATOR_URL=$(gcloud run services describe regulator-agent --region=$REGION --format='value(status.url)')

curl -X POST $REGULATOR_URL/check_risk \
-H "Content-Type: application/json" \
-d '{"zone": "Cape Foulweather"}'
```

