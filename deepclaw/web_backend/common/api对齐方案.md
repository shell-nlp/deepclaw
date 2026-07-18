# API 对齐方案
## 测试URL
- V1版本：7869/api/agent/general_api 
- V2版本：7869/api/agent/v2/general_api
## 测试目的
保证 v2 版本的 API 输出向 v1 版本对齐，包括响应体、错误码等。

## 可参考文档
### langchain 文档
- https://docs.langchain.com/oss/python/langchain/event-streaming
- https://docs.langchain.com/oss/python/langchain/overview
## 接口请求体示例
```json
{
    "query": "南京天气怎么样",
    "deep_thinking": true,
    "stream":true
}
```
## 测试方法
使用 python 脚本测试进行调用测试
### 开启思考模式
#### 测试如下问题
- 你好，你是谁？
- 郑州的天气怎么样？
- 南京和北京的天气怎么样？
- 南阳天气怎么样？

**注释：南阳天气怎么样？ 这个问题是专门来测试 __interrupt__ **
## 暂时可不对齐的内容
- usage_metadata 出现频率
- 首帧 / 增量帧行为差异
## 其它测试要求
"stream":true 和 "stream":false  也要进行测试，也要对齐 v1 版本的输出。