pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '5'))
        disableConcurrentBuilds()
        timestamps()
        skipDefaultCheckout(true)
    }

    parameters {
        string(name: 'AWS_ACCESS_KEY_ID', defaultValue: '', description: 'Access Key de AWS Learner Lab')
        password(name: 'AWS_SECRET_ACCESS_KEY', defaultValue: '', description: 'Secret Access Key de AWS Learner Lab')
        password(name: 'AWS_SESSION_TOKEN', defaultValue: '', description: 'Session Token de AWS Learner Lab (Obligatorio en Learner Lab)')
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

        stage('Deploy Dev') {
            when { branch 'development' }
            steps {
                deployServerless('dev')
            }
        }

        stage('Deploy QA') {
            when { branch 'qa' }
            steps {
                deployServerless('qa')
            }
        }

        stage('Deploy UAT') {
            when { branch 'uat' }
            steps {
                deployServerless('uat')
            }
        }

        stage('Deploy Prod') {
            when { branch 'main' }
            steps {
                deployServerless('prod')
            }
        }
    }
}

// Función auxiliar para realizar el deploy instalando Serverless en el contenedor Node
def deployServerless(String targetStage) {
    docker.image('node:24-alpine').inside {
        withEnv([
            "AWS_ACCESS_KEY_ID=${params.AWS_ACCESS_KEY_ID}",
            "AWS_SECRET_ACCESS_KEY=${params.AWS_SECRET_ACCESS_KEY}",
            "AWS_SESSION_TOKEN=${params.AWS_SESSION_TOKEN}",
            "AWS_DEFAULT_REGION=us-east-1"
        ]) {
            sh """
                npm install -g serverless
                serverless deploy --stage ${targetStage}
            """
        }
    }
}