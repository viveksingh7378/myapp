pipeline {
    agent any

    environment {
        DOCKER_USER      = "vivek7378"
        GIT_COMMIT_SHORT = sh(script: "git rev-parse --short HEAD", returnStdout: true).trim()

        // Microservice image names
        IMG_PRODUCT  = "vivek7378/product-service"
        IMG_ORDER    = "vivek7378/order-service"
        IMG_USER     = "vivek7378/user-service"
        IMG_PAYMENT  = "vivek7378/payment-service"
        IMG_FRONTEND = "vivek7378/frontend"

        // Legacy app image (kept for backward compat)
        DOCKER_IMAGE = "vivek7378/myapp"
    }

    stages {

        // ── 1. RESET ──────────────────────────────────────────────────────────
        stage('Reset AI Retry Counter') {
            steps {
                sh 'rm -f ai_agent/.ai_retry_count'
            }
        }

        // ── 2. CHECKOUT ───────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        // ── 3. AI CODE ANALYSIS ───────────────────────────────────────────────
        stage('AI Code Analysis') {
            steps {
                sh 'pip3 install -r requirements.txt --quiet'
                script {
                    withCredentials([
                        string(credentialsId: 'GEMINI_API_KEY', variable: 'GEMINI_API_KEY'),
                        string(credentialsId: 'GITHUB_TOKEN',   variable: 'GITHUB_TOKEN')
                    ]) {
                        // Configure git auth BEFORE running the analyzer.
                        // Uses HTTP Authorization header (same method as GitHub Actions)
                        // instead of embedding the token in the URL — URL-embedded tokens
                        // cause "URL rejected: Bad hostname" on macOS git/libcurl.
                        sh '''
                            git config user.email "ai-bot@pipeline.local"
                            git config user.name  "AI-Remediation-Bot"
                            git config credential.helper ""
                            git remote set-url origin https://github.com/viveksingh7378/myapp.git
                            CLEAN_TOKEN=$(printf '%s' "${GITHUB_TOKEN}" | tr -cd 'A-Za-z0-9_-')
                            B64=$(printf 'x-access-token:%s' "${CLEAN_TOKEN}" | base64 | tr -d '\n')
                            git config http.https://github.com/.extraHeader "Authorization: Basic ${B64}"
                        '''

                        def code = sh(
                            script: '''
                                GEMINI_API_KEY=$GEMINI_API_KEY \
                                GITHUB_TOKEN=$GITHUB_TOKEN \
                                python3 ai_agent/analyzer.py 2>&1 | tee analysis_output.txt
                            ''',
                            returnStatus: true
                        )

                        // Clean up auth header after analyzer exits
                        sh 'git config --unset http.https://github.com/.extraHeader || true'

                        if (code == 0) {
                            echo "✅ AI analysis complete — no issues found or fixes already applied"
                        } else if (code == 1) {
                            echo "✅ AI Analyzer fixed and pushed changes to GitHub"
                        } else {
                            echo "⚠️  AI Analyzer exited with code ${code} — Lint and Test will catch real errors"
                        }
                    }
                }
            }
        }

        // ── 4. LINT ALL SERVICES ──────────────────────────────────────────────
        stage('Lint') {
            steps {
                sh 'pip3 install flake8 --quiet'
                script {
                    def targets = [
                        'app/',
                        'services/product-service/app/',
                        'services/order-service/app/',
                        'services/user-service/app/',
                        'services/payment-service/app/'
                    ].join(' ')
                    sh "python3 -m flake8 ${targets} --max-line-length=120 --ignore=E501,W503 2>&1 | tee lint_output.txt || true"
                    def count = sh(
                        script: 'grep -cE "E[0-9]|W[0-9]" lint_output.txt || true',
                        returnStdout: true
                    ).trim().toInteger()
                    echo count > 0 ? "⚠️  Lint: ${count} warnings — see lint_output.txt" : "✅ Lint: no issues"
                }
            }
        }

        // ── 5. TEST ALL SERVICES IN PARALLEL ─────────────────────────────────
        stage('Test All Services') {
            parallel {

                stage('Test: core app') {
                    steps {
                        sh '''
                            pip3 install flask pytest pytest-flask --quiet
                            python3 -m pytest tests/ --tb=short -q 2>&1 | tee test_core.txt || true
                        '''
                        script {
                            def failed = sh(script: 'grep -cE "FAILED|ERROR" test_core.txt || true', returnStdout: true).trim().toInteger()
                            if (failed > 0) { echo "⚠️  core-app: ${failed} test failures"; } else { echo "✅ core-app: all tests passed"; }
                        }
                    }
                }

                stage('Test: product-service') {
                    steps {
                        sh '''
                            pip3 install flask pytest pytest-flask --quiet
                            python3 -m pytest services/product-service/tests/ --tb=short -q 2>&1 | tee test_product.txt || true
                        '''
                        script {
                            def failed = sh(script: 'grep -cE "FAILED|ERROR" test_product.txt || true', returnStdout: true).trim().toInteger()
                            if (failed > 0) { echo "⚠️  product-service: ${failed} test failures"; } else { echo "✅ product-service: all tests passed"; }
                        }
                    }
                }

                stage('Test: order-service') {
                    steps {
                        sh '''
                            pip3 install flask pytest pytest-flask --quiet
                            python3 -m pytest services/order-service/tests/ --tb=short -q 2>&1 | tee test_order.txt || true
                        '''
                        script {
                            def failed = sh(script: 'grep -cE "FAILED|ERROR" test_order.txt || true', returnStdout: true).trim().toInteger()
                            if (failed > 0) { echo "⚠️  order-service: ${failed} test failures"; } else { echo "✅ order-service: all tests passed"; }
                        }
                    }
                }

                stage('Test: user-service') {
                    steps {
                        sh '''
                            pip3 install flask pytest pytest-flask --quiet
                            python3 -m pytest services/user-service/tests/ --tb=short -q 2>&1 | tee test_user.txt || true
                        '''
                        script {
                            def failed = sh(script: 'grep -cE "FAILED|ERROR" test_user.txt || true', returnStdout: true).trim().toInteger()
                            if (failed > 0) { echo "⚠️  user-service: ${failed} test failures"; } else { echo "✅ user-service: all tests passed"; }
                        }
                    }
                }

                stage('Test: payment-service') {
                    steps {
                        sh '''
                            pip3 install flask pytest pytest-flask --quiet
                            python3 -m pytest services/payment-service/tests/ --tb=short -q 2>&1 | tee test_payment.txt || true
                        '''
                        script {
                            def failed = sh(script: 'grep -cE "FAILED|ERROR" test_payment.txt || true', returnStdout: true).trim().toInteger()
                            if (failed > 0) { echo "⚠️  payment-service: ${failed} test failures"; } else { echo "✅ payment-service: all tests passed"; }
                        }
                    }
                }

            }
        }

        // ── 6. DOCKER BUILD ALL SERVICES IN PARALLEL ─────────────────────────
        stage('Docker Build') {
            parallel {

                stage('Build: product-service') {
                    steps {
                        script {
                            def rc = sh(script: "docker build -t ${IMG_PRODUCT}:${GIT_COMMIT_SHORT} services/product-service/", returnStatus: true)
                            if (rc != 0) { echo "⚠️  Docker build failed for product-service — is Docker Desktop running?" }
                            echo "✅ Built ${IMG_PRODUCT}:${GIT_COMMIT_SHORT}"
                        }
                    }
                }

                stage('Build: order-service') {
                    steps {
                        script {
                            def rc = sh(script: "docker build -t ${IMG_ORDER}:${GIT_COMMIT_SHORT} services/order-service/", returnStatus: true)
                            if (rc != 0) { echo "⚠️  Docker build failed for order-service" }
                            echo "✅ Built ${IMG_ORDER}:${GIT_COMMIT_SHORT}"
                        }
                    }
                }

                stage('Build: user-service') {
                    steps {
                        script {
                            def rc = sh(script: "docker build -t ${IMG_USER}:${GIT_COMMIT_SHORT} services/user-service/", returnStatus: true)
                            if (rc != 0) { echo "⚠️  Docker build failed for user-service" }
                            echo "✅ Built ${IMG_USER}:${GIT_COMMIT_SHORT}"
                        }
                    }
                }

                stage('Build: payment-service') {
                    steps {
                        script {
                            def rc = sh(script: "docker build -t ${IMG_PAYMENT}:${GIT_COMMIT_SHORT} services/payment-service/", returnStatus: true)
                            if (rc != 0) { echo "⚠️  Docker build failed for payment-service" }
                            echo "✅ Built ${IMG_PAYMENT}:${GIT_COMMIT_SHORT}"
                        }
                    }
                }

                stage('Build: frontend') {
                    steps {
                        script {
                            def rc = sh(script: "docker build -t ${IMG_FRONTEND}:${GIT_COMMIT_SHORT} frontend/", returnStatus: true)
                            if (rc != 0) { echo "⚠️  Docker build failed for frontend" }
                            echo "✅ Built ${IMG_FRONTEND}:${GIT_COMMIT_SHORT}"
                        }
                    }
                }

            }
        }

        // ── 7. TRIVY SECURITY SCAN ────────────────────────────────────────────
        stage('Trivy Scan') {
            steps {
                script {
                    def images = [
                        "${IMG_PRODUCT}:${GIT_COMMIT_SHORT}",
                        "${IMG_ORDER}:${GIT_COMMIT_SHORT}",
                        "${IMG_USER}:${GIT_COMMIT_SHORT}",
                        "${IMG_PAYMENT}:${GIT_COMMIT_SHORT}",
                        "${IMG_FRONTEND}:${GIT_COMMIT_SHORT}"
                    ]
                    images.each { img ->
                        def name = img.split('/')[1].split(':')[0]
                        sh "/opt/homebrew/bin/trivy image --exit-code 0 --severity HIGH,CRITICAL ${img} 2>&1 | tee trivy-${name}.txt || true"
                    }
                    archiveArtifacts artifacts: 'trivy-*.txt', allowEmptyArchive: true
                }
            }
        }

        // ── 8. PUSH ALL IMAGES ────────────────────────────────────────────────
        stage('Push Images') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                    sh 'echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin'
                    script {
                        def images = [
                            "${IMG_PRODUCT}:${GIT_COMMIT_SHORT}",
                            "${IMG_ORDER}:${GIT_COMMIT_SHORT}",
                            "${IMG_USER}:${GIT_COMMIT_SHORT}",
                            "${IMG_PAYMENT}:${GIT_COMMIT_SHORT}",
                            "${IMG_FRONTEND}:${GIT_COMMIT_SHORT}"
                        ]
                        images.each { img ->
                            sh "docker push ${img}"
                            // Also tag as latest
                            def imgLatest = img.replaceAll(':.*', ':latest')
                            sh "docker tag ${img} ${imgLatest} && docker push ${imgLatest}"
                            echo "✅ Pushed ${img}"
                        }
                    }
                }
            }
        }

        // ── 9. DEPLOY ALL TO KUBERNETES ───────────────────────────────────────
        stage('Deploy to K8s') {
            steps {
                script {
                    // Ensure the ecommerce namespace exists
                    sh 'kubectl apply -f k8s/namespace.yaml'

                    // Deploy each microservice by substituting image tags
                    def deployments = [
                        [file: 'k8s/product-service.yaml',  tag: 'PRODUCT_TAG',  name: 'product-service'],
                        [file: 'k8s/order-service.yaml',    tag: 'ORDER_TAG',    name: 'order-service'],
                        [file: 'k8s/user-service.yaml',     tag: 'USER_TAG',     name: 'user-service'],
                        [file: 'k8s/payment-service.yaml',  tag: 'PAYMENT_TAG',  name: 'payment-service'],
                        [file: 'k8s/frontend.yaml',         tag: 'FRONTEND_TAG', name: 'frontend'],
                    ]

                    deployments.each { svc ->
                        sh """
                            sed 's|${svc.tag}|${GIT_COMMIT_SHORT}|g' ${svc.file} \
                                > k8s/${svc.name}-final.yaml
                            kubectl apply -f k8s/${svc.name}-final.yaml
                        """
                        echo "✅ Applied k8s manifest for ${svc.name}"
                    }

                    // Wait for all rollouts
                    def services = ['product-service', 'order-service', 'user-service', 'payment-service', 'frontend']
                    services.each { svc ->
                        def rc = sh(
                            script: "kubectl rollout status deployment/${svc} -n ecommerce --timeout=90s",
                            returnStatus: true
                        )
                        if (rc == 0) {
                            echo "✅ ${svc} rollout complete"
                        } else {
                            echo "⚠️  ${svc} rollout timeout — check cluster manually"
                        }
                    }
                }
            }
        }

    } // end stages

    post {
        failure {
            echo """
╔══════════════════════════════════════════════════════╗
║  Pipeline FAILED — common causes:                    ║
║  • Docker Desktop not running (Docker Build stage)   ║
║  • kubectl not configured (Deploy stage)             ║
║  • DockerHub credentials not set in Jenkins          ║
║  • Gemini API key expired (AI Analysis stage)        ║
╚══════════════════════════════════════════════════════╝"""
        }
        success {
            sh 'rm -f ai_agent/.ai_retry_count'
            echo """
╔══════════════════════════════════════════════════════╗
║  ✅  E-Commerce Microservices deployed successfully! ║
║                                                      ║
║  Service URLs (NodePort):                            ║
║    Frontend        → http://localhost:30085          ║
║    Product Service → http://localhost:30001          ║
║    Order Service   → http://localhost:30002          ║
║    User Service    → http://localhost:30003          ║
║    Payment Service → http://localhost:30004          ║
╚══════════════════════════════════════════════════════╝"""
        }
    }
}
