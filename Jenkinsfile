pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: jenkins
  containers:
    - name: jnlp
      image: localhost:32000/jenkins-inbound-agent:lab
    - name: tools
      image: localhost:32000/python-ci:lab
      command: ['cat']
      tty: true
'''
        }
    }

    environment {
        TERRAFORM  = "/usr/local/bin/terraform"
        PLUGINS    = "/usr/local/terraform-plugins"
    }

    stages {

        // ── Concept: Declarative IaC — describe desired state, Terraform
        //    calculates what needs to change and applies only the diff.
        //    Jenkins (devops namespace) is never in Terraform state.
        stage('Terraform Apply') {
            steps {
                container('tools') {
                    dir('terraform') {
                        sh '$TERRAFORM init -input=false -plugin-dir=$PLUGINS'
                        sh '$TERRAFORM apply -auto-approve'
                        sh '$TERRAFORM show'   // log declared state as proof
                    }
                }
            }
        }

        // ── Concept: Ephemeral Environments — policy and app source are
        //    materialized as ConfigMaps from the Jenkins workspace, since
        //    hostPath cannot be used (build pod and target pods may land
        //    on different nodes / different filesystems entirely).
        stage('Deploy OPA & App') {
            steps {
                container('tools') {
                    sh '''
                        kubectl create configmap opa-policy -n lab9 \
                          --from-file=policy.rego=opa/policy.rego \
                          --dry-run=client -o yaml | kubectl apply -f -

                        kubectl create configmap lab9-app-src -n lab9 \
                          --from-file=server.py=app/server.py \
                          --dry-run=client -o yaml | kubectl apply -f -

                        kubectl apply -f k8s/opa.yaml
                        kubectl apply -f k8s/app.yaml

                        kubectl rollout status deployment/opa -n lab9 --timeout=90s
                        kubectl rollout status deployment/lab9-app -n lab9 --timeout=90s
                        kubectl get pods,svc -n lab9
                    '''
                }
            }
        }

        // ── Concept: Drift Detection — simulate an ops engineer manually
        //    patching the resource quota (a common real-world drift scenario).
        //    Terraform detects the out-of-band change and corrects it.
        stage('Drift Detection') {
            steps {
                container('tools') {
                    sh '''
                        echo "==> Simulating drift: patching limits.cpu to 2000m"
                        kubectl patch resourcequota lab9-quota -n lab9 \
                          --type=merge \
                          -p '{"spec":{"hard":{"limits.cpu":"2000m"}}}'

                        echo ""
                        echo "==> Quota after manual patch (should show 2000m):"
                        kubectl get resourcequota lab9-quota -n lab9 -o yaml | grep "limits.cpu"

                        echo ""
                        echo "==> terraform plan — drift should be detected:"
                        cd $WORKSPACE/terraform
                        $TERRAFORM plan -detailed-exitcode 2>&1 || PLAN_EXIT=$?
                        if [ "${PLAN_EXIT:-0}" -eq 2 ]; then
                            echo "DRIFT DETECTED — Terraform found changes outside its control"
                        fi

                        echo ""
                        echo "==> Correcting drift:"
                        $TERRAFORM apply -auto-approve

                        echo ""
                        echo "==> Quota after correction (should show 1000m):"
                        kubectl get resourcequota lab9-quota -n lab9 -o yaml | grep "limits.cpu"
                    '''
                }
            }
        }

        // ── Concept: Policy-as-Code — OPA evaluates every request against
        //    the Rego policy file and returns true/false. Tests run inside
        //    the OPA pod via kubectl exec — no port-forwarding needed.
        stage('OPA Smoke Tests') {
            steps {
                container('tools') {
                    sh '''
                        opa_test() {
                            local desc="$1" user="$2" action="$3" expect="$4"
                            PAYLOAD='{"input": {"user": "'"$user"'", "action": "'"$action"'"}}'
                            RESULT=$(kubectl exec -n lab9 deploy/opa -- \
                            wget -qO- \
                            --post-data "$PAYLOAD" \
                            --header "Content-Type: application/json" \
                            http://localhost:8181/v1/data/lab/allow 2>/dev/null)
                            ACTUAL=$(echo "$RESULT" | python3 -c \
                            "import sys,json; print(json.load(sys.stdin).get('result', False))" 2>/dev/null)
                            if [ "$ACTUAL" = "$expect" ]; then
                                echo "  PASS  $desc"
                            else
                                echo "  FAIL  $desc — expected=$expect actual=$ACTUAL raw=$RESULT"
                                exit 1
                            fi
                        }

                        echo ""
                        echo "==> OPA Policy Smoke Tests"
                        echo "-------------------------------------------"
                        opa_test "alice  + read   (should be allowed)"  alice  read   True
                        opa_test "alice  + list   (should be allowed)"  alice  list   True
                        opa_test "bob    + read   (should be allowed)"  bob    read   True
                        opa_test "alice  + delete (should be denied)"   alice  delete False
                        opa_test "eve    + read   (should be denied)"   eve    read   False
                        opa_test "admin  + delete (should be allowed)"  admin  delete True
                        opa_test "admin  + read   (should be allowed)"  admin  read   True
                        echo "-------------------------------------------"
                        echo "All OPA smoke tests passed"
                    '''
                }
            }
        }

        // ── Concept: End-to-end validation — the app is tested directly
        //    via kubectl exec to confirm health and OPA integration.
        stage('App Smoke Tests') {
            steps {
                container('tools') {
                    sh '''
                        app_test() {
                            local desc="$1" path="$2" expect_allowed="$3"
                            RESULT=$(kubectl exec -n lab9 deploy/lab9-app -- \
                            curl -s "http://127.0.0.1:3000${path}" 2>/dev/null)
                            echo "  $desc → $RESULT"
                            if [ -n "$expect_allowed" ]; then
                                ACTUAL=$(echo "$RESULT" | python3 -c \
                                "import sys,json; print(json.load(sys.stdin).get('allowed', False))" 2>/dev/null)
                                if [ "$ACTUAL" = "$expect_allowed" ]; then
                                    echo "  PASS"
                                else
                                    echo "  FAIL — expected allowed=$expect_allowed got=$ACTUAL"
                                    exit 1
                                fi
                            fi
                        }

                        echo ""
                        echo "==> App Smoke Tests"
                        echo "-------------------------------------------"
                        app_test "GET /health"                          "/health"                      ""
                        app_test "alice + read  (allowed=True)"        "/check?user=alice&action=read" "True"
                        app_test "eve   + read  (allowed=False)"       "/check?user=eve&action=read"   "False"
                        app_test "admin + delete (allowed=True)"       "/check?user=admin&action=delete" "True"
                        echo "-------------------------------------------"
                        echo "All app smoke tests passed"
                    '''
                }
            }
        }
        // ── Concept: Policy is live-updatable — add charlie without touching
        //    any application code. Since policy.rego is served from a
        //    ConfigMap (not a hostPath), the ConfigMap must be re-created
        //    from the edited file, then the OPA deployment restarted so it
        //    re-reads the new mounted content.
        stage('Policy Update: Add charlie') {
            steps {
                container('tools') {
                    sh '''
                        echo "==> Updating policy: adding charlie to allowed_users"
                        sed -i 's/allowed_users := {"alice", "bob", "admin"}/allowed_users := {"alice", "bob", "admin", "charlie"}/' opa/policy.rego
                        grep "allowed_users" opa/policy.rego

                        echo "==> Re-creating opa-policy ConfigMap from updated file"
                        kubectl create configmap opa-policy -n lab9 \
                          --from-file=policy.rego=opa/policy.rego \
                          --dry-run=client -o yaml | kubectl apply -f -

                        kubectl rollout restart deployment/opa -n lab9
                        kubectl rollout status deployment/opa -n lab9 --timeout=60s
                        sleep 2

                        echo ""
                        echo "==> charlie + read (should be True):"
                        RESULT=$(kubectl exec -n lab9 deploy/opa -- \
                          wget -qO- \
                          --post-data '{"input": {"user": "charlie", "action": "read"}}' \
                          --header "Content-Type: application/json" \
                          http://localhost:8181/v1/data/lab/allow 2>/dev/null)
                        echo "charlie + read → $RESULT"
                        echo "$RESULT" | python3 -c \
                          "import sys,json; r=json.load(sys.stdin); exit(0 if r.get('result') else 1)" \
                          || (echo "FAIL: charlie should be allowed after policy update" && exit 1)
                        echo "PASS"
                    '''
                }
            }
        }

        // ── Concept: New policy rules are code — add an admin-only delete
        //    restriction without modifying any application code. Same
        //    ConfigMap re-create + restart pattern as above.
        stage('Policy Update: Admin-only Delete Rule') {
            steps {
                container('tools') {
                    sh '''
                        echo "==> Appending deny_delete rule to policy.rego"
                        cat >> opa/policy.rego << 'REGO'

                        # Nobody except admin can delete
                        deny_delete if {
                            input.action == "delete"
                            input.user != "admin"
                        }
                        REGO

                        echo "==> Re-creating opa-policy ConfigMap from updated file"
                        kubectl create configmap opa-policy -n lab9 \
                          --from-file=policy.rego=opa/policy.rego \
                          --dry-run=client -o yaml | kubectl apply -f -

                        kubectl rollout restart deployment/opa -n lab9
                        kubectl rollout status deployment/opa -n lab9 --timeout=60s
                        sleep 2

                        echo ""
                        echo "==> alice + delete (should be False):"
                        RESULT=$(kubectl exec -n lab9 deploy/opa -- \
                          wget -qO- \
                          --post-data '{"input": {"user": "alice", "action": "delete"}}' \
                          --header "Content-Type: application/json" \
                          http://localhost:8181/v1/data/lab/allow 2>/dev/null)
                        echo "alice + delete → $RESULT"
                        echo "$RESULT" | python3 -c \
                          "import sys,json; r=json.load(sys.stdin); exit(1 if r.get('result') else 0)" \
                          || (echo "FAIL: alice delete should be denied" && exit 1)
                        echo "PASS"

                        echo ""
                        echo "==> admin + delete (should be True):"
                        RESULT=$(kubectl exec -n lab9 deploy/opa -- \
                          wget -qO- \
                          --post-data '{"input": {"user": "admin", "action": "delete"}}' \
                          --header "Content-Type: application/json" \
                          http://localhost:8181/v1/data/lab/allow 2>/dev/null)
                        echo "admin + delete → $RESULT"
                        echo "$RESULT" | python3 -c \
                          "import sys,json; r=json.load(sys.stdin); exit(0 if r.get('result') else 1)" \
                          || (echo "FAIL: admin delete should be allowed" && exit 1)
                        echo "PASS"
                    '''
                }
            }
        }

        // ── Concept: Full teardown — lab9 is destroyed by Terraform.
        //    Jenkins in devops is deleted separately.
        //    Nothing is left behind.
        stage('Teardown') {
            steps {
                container('tools') {
                    sh '''
                        echo "==> Destroying lab9 environment via Terraform"
                        cd $WORKSPACE/terraform
                        $TERRAFORM destroy -auto-approve

                        echo ""
                        echo "==> Verifying lab9 namespace is gone:"
                        kubectl get namespace lab9 2>&1 || true
                        
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'pkill -f "port-forward" || true'
        }
        success {
            echo 'All stages passed — lab complete'
        }
        failure {
            container('tools') {
                sh 'kubectl get pods -n lab9 || true'
                sh 'kubectl get pods -n devops || true'
                sh 'kubectl describe pods -n lab9 || true'
            }
            echo 'Pipeline failed — check stage logs above'
        }
    }
}