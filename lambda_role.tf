resource "aws_iam_role" "iam_role_for_lambda" {
  name               = "role_for_lambda"
  assume_role_policy = file("iam/lambda_assume_role.json")
}
resource "aws_iam_policy" "lambda_logging" {
  name        = "lambda_cloudwatch_log"
  description = "IAM policy for logging from a lambda"
  path = "/"
  policy = file("iam/lambda_cloudwatch_policy.json")
}
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.iam_role_for_lambda.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}