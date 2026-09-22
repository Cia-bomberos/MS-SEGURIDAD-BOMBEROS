pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '5'))
        disableConcurrentBuilds()
        timestamps()
        skipDefaultCheckout(true)
    }

    // Parámetros para ingresar las credenciales dinámicas de AWS Learner Lab
    parameters {
        string(name: 'AWS_ACCESS_KEY_ID', defaultValue: '', description: 'Access Key de AWS Learner Lab')
        password(name: 'AWS_SECRET_ACCESS_KEY', defaultValue: '', description: 'Secret Access Key de AWS Learner Lab')
        password(name: 'AWS_SESSION_TOKEN', defaultValue: '', description: 'Session Token de AWS Learner Lab')
    }

    stages {
        stage('Checkout Repo') {
            steps {
                checkout scm
            }
        }

        stage('Test & Coverage (Python)') {
            agent {
                docker {
                    image 'python:3.12-alpine'
                    reuseNode true
                }
            }
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --no-cache-dir -r requirements-dev.txt
                    pytest tests/ \
                        --cov=modulo_admin \
                        --cov-report=xml:coverage.xml \
                        --cov-report=term
                '''
            }
        }

        stage('SonarQube Analysis') {
            when {
                anyOf {
                    branch 'qa'
                    branch 'uat'
                    branch 'main'
                }
            }
            agent {
                dockerfile {
                    filename 'Dockerfile.ci'
                    reuseNode true
                }
            }
            environment {
                scannerHome = tool 'SonarScanner'
            }
            steps {
                script {
                    def sonarUserHome = "${env.WORKSPACE}/.sonar"

                    withEnv(["SONAR_USER_HOME=${sonarUserHome}"]) {
                        def projectKey = "BE-BOMBEROS-${env.BRANCH_NAME.toUpperCase()}"
                        
                        withSonarQubeEnv('SonarQube-Server') {
                            sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectKey=${projectKey} -Dsonar.userHome=${sonarUserHome}"
                        }
                    }
                }
            }
        }

        stage('Quality Gate') {
            when {
                anyOf {
                    branch 'qa'
                    branch 'uat'
                    branch 'main'
                }
            }
            steps {
                timeout(time: 1, unit: 'HOURS') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        // --- STAGES DE DEPLOY TRADUCIDOS DESDE TU DEPLOY.YML ---

        stage('Deploy Dev') {
            when { branch 'development' }
            steps {
                executeServerlessDeploy('dev')
            }
        }

        stage('Deploy QA') {
            when { branch 'qa' }
            steps {
                executeServerlessDeploy('qa')
            }
        }

        stage('Deploy UAT') {
            when { branch 'uat' }
            steps {
                executeServerlessDeploy('uat')
            }
        }

        stage('Deploy Prod') {
            when { branch 'main' }
            steps {
                executeServerlessDeploy('prod')
            }
        }
    }
}

// Función que ejecuta exactamente los pasos de tu GitHub Actions dentro de un contenedor Node.js
def executeServerlessDeploy(String targetStage) {
    docker.image('node:20').inside {
        withEnv([
            "AWS_ACCESS_KEY_ID=${params.AWS_ACCESS_KEY_ID}",
            "AWS_SECRET_ACCESS_KEY=${params.AWS_SECRET_ACCESS_KEY}",
            "AWS_SESSION_TOKEN=${params.AWS_SESSION_TOKEN}",
            "AWS_DEFAULT_REGION=us-east-1",
            "NPM_CONFIG_PREFIX=${env.WORKSPACE}/.npm-global"
        ]) {
            sh """
                npm install -g serverless@3
                ./.npm-global/bin/serverless deploy --stage ${targetStage} --verbose
            """
        }
    }
}