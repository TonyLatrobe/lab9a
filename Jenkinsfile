pipeline {
    agent any

    environment {
        TERRAFORM = "/home/cse2001/lab-images/python-agent/terraform-bin/terraform"
        PLUGINS   = "/home/cse2001/lab-images/python-agent/terraform-bundle"
    }

    stages {

        // ==========================================================
        // SETUP KUBERNETES ACCESS (NO SUDO, MICROK8S DIRECT)
        // ==========================================================
        stage('Setup Cluster Access') {
            steps {
                sh '''
                    set -e

                    echo "Checking MicroK8s availability..."
                    microk8s status --wait-ready

                    echo "Testing cluster access..."
                    microk8s kubectl get nodes

                    echo "Cluster access OK"
                '''
            }
        }

        // ==========================================================
        // TERRAFORM APPLY
        // ==========================================================
        stage('Terraform Apply') {
            steps {
                dir('terraform') {
                    sh '''
                        set -e

                        echo "Running Terraform Init..."
                        $TERRAFORM init -input=false -plugin-dir=$PLUGINS

                        echo "Running Terraform Apply..."
                        $TERRAFORM apply -auto-approve

                        echo "Terraform State:"
                        $TERRAFORM show
                    '''
                }
            }
        }

        // ==========================================================
        // DEPLOY OPA + APP
        // ==========================================================
        stage('Deploy OPA & App') {
            steps {
                sh '''
                    set -e

                    microk8s kubectl create namespace lab9 --dry-run=client -o yaml | microk8s kubectl apply -f -

                    microk8s kubectl apply -f k8s/opa.yaml
                    microk8s kubectl apply -f k8s/app.yaml

                    microk8s kubectl rollout status deployment/opa -n lab9 --timeout=120s
                    microk8s kubectl rollout status deployment/lab9-app -n lab9 --timeout=120s

                    microk8s kubectl get pods,svc -n lab9
                '''
            }
        }

        // ==========================================================
        // DRIFT DETECTION
        // ==========================================================
        stage('Drift Detection') {
            steps {
                sh '''
                    set -e

                    echo "Simulating drift..."
                    microk8s kubectl patch resourcequota lab9-quota -n lab9 \
                      --type=merge \
                      -p '{"spec":{"hard":{"limits.cpu":"2000m"}}}'

                    echo "Running Terraform Plan..."
                    cd terraform

                    set +e
                    $TERRAFORM plan -detailed-exitcode
                    EXIT=$?
                    set -e

                    if [ $EXIT -eq 2 ]; then
                        echo "DRIFT DETECTED"
                    fi

                    echo "Applying correction..."
                    $TERRAFORM apply -auto-approve
                '''
            }
        }

        // ==========================================================
        // OPA SMOKE TESTS
        // ==========================================================
        stage('OPA Smoke Tests') {
            steps {
                sh '''
                    set -e

                    opa_test () {
                        DESC=$1
                        USER=$2
                        ACTION=$3
                        EXPECT=$4

                        RESULT=$(microk8s kubectl exec -n lab9 deploy/opa -- \
                          wget -qO- \
                          --post-data "{\"input\":{\"user\":\"$USER\",\"action\":\"$ACTION\"}}" \
                          --header "Content-Type: application/json" \
                          http://localhost:8181/v1/data/lab/allow)

                        ACTUAL=$(echo "$RESULT" | python3 -c \
                          "import sys,json; print(json.load(sys.stdin).get('result', False))")

                        if [ "$ACTUAL" = "$EXPECT" ]; then
                            echo "PASS: $DESC"
                        else
                            echo "FAIL: $DESC"
                            exit 1
                        fi
                    }

                    opa_test "alice read" alice read True
                    opa_test "alice delete" alice delete False
                    opa_test "admin delete" admin delete True
                '''
            }
        }

        // ==========================================================
        // APP SMOKE TESTS
        // ==========================================================
        stage('App Smoke Tests') {
            steps {
                sh '''
                    set -e

                    app_test () {
                        DESC=$1
                        PATH=$2
                        EXPECT=$3

                        RESULT=$(microk8s kubectl exec -n lab9 deploy/lab9-app -- \
                          wget -qO- "http://localhost:3000${PATH}")

                        echo "$RESULT"

                        ACTUAL=$(echo "$RESULT" | python3 -c \
                          "import sys,json; print(json.load(sys.stdin).get('allowed', False))")

                        if [ "$ACTUAL" = "$EXPECT" ]; then
                            echo "PASS: $DESC"
                        else
                            echo "FAIL: $DESC"
                            exit 1
                        fi
                    }

                    app_test "health" "/health" ""
                    app_test "alice read" "/check?user=alice&action=read" True
                    app_test "eve read" "/check?user=eve&action=read" False
                '''
            }
        }

        // ==========================================================
        // POLICY UPDATE: ADD CHARLIE
        // ==========================================================
        stage('Policy Update: Add charlie') {
            steps {
                sh '''
                    set -e

                    sed -i 's/allowed_users := {"alice", "bob", "admin"}/allowed_users := {"alice", "bob", "admin", "charlie"}/' opa/policy.rego

                    microk8s kubectl rollout restart deployment/opa -n lab9
                    microk8s kubectl rollout status deployment/opa -n lab9 --timeout=120s
                '''
            }
        }

        // ==========================================================
        // POLICY UPDATE: ADMIN DELETE RULE
        // ==========================================================
        stage('Policy Update: Admin-only Delete Rule') {
            steps {
                sh '''
                    set -e

                    cat >> opa/policy.rego << 'EOF'

                    deny_delete if {
                        input.action == "delete"
                        input.user != "admin"
                    }
                    EOF

                    microk8s kubectl rollout restart deployment/opa -n lab9
                    microk8s kubectl rollout status deployment/opa -n lab9 --timeout=120s
                '''
            }
        }

        // ==========================================================
        // TEARDOWN
        // ==========================================================
        stage('Teardown') {
            steps {
                sh '''
                    set -e

                    cd terraform
                    $TERRAFORM destroy -auto-approve

                    microk8s kubectl delete namespace lab9 --ignore-not-found=true
                    microk8s kubectl delete namespace devops --ignore-not-found=true || true
                '''
            }
        }
    }

    post {
        always {
            sh 'pkill -f port-forward || true'
        }

        failure {
            sh '''
                microk8s kubectl get pods -A || true
                microk8s kubectl describe pods -n lab9 || true
            '''
            echo "Pipeline failed — check logs above"
        }

        success {
            echo "All stages passed — lab complete"
        }
    }
}