# G2-06A Normalization Mutation Validation Design

## Mục tiêu

Chứng minh `SemanticNormalizer` loại bỏ đúng nhiễu động nhưng vẫn giữ lại sai khác nghiệp vụ, schema và kiểu dữ liệu. Validation dùng các cặp JSON fixture biến đổi có kiểm soát, chạy offline và xác định hoàn toàn.

## Phạm vi

- Thêm cấu hình runtime riêng tại `config/normalization-rules.json`.
- Thêm endpoint scope chính xác theo chuỗi `METHOD /path`.
- Thêm action `MASK_STRING` để mask giá trị chuỗi nhưng bảo toàn lỗi missing, `null` và sai kiểu.
- Kiểm chứng `MASK_STRING`, `REGEX_REPLACE`, `MAP_STATE`, wildcard và endpoint scope bằng mutation fixtures.
- Giữ `DROP` để tương thích engine hiện có.
- Không sửa `config/ignore-rules.json`; đây tiếp tục là catalog/evidence do G2-02 sinh.

Ngoài phạm vi: comparator/reporting mới, chuyển đổi tự động catalog G2-02, test Jellyfin/Docker, mutation ngẫu nhiên, property-based testing và dependency mới.

## Contract cấu hình runtime

File runtime có root object chứa `rules`. Mỗi rule bắt buộc có:

- `endpoint`: string đúng dạng `METHOD /path`, ví dụ `POST /Users/AuthenticateByName`.
- `path`: JSONPath thuộc cú pháp field và `[*]` hiện được hỗ trợ.
- `action`: một trong `DROP`, `MASK_STRING`, `REGEX_REPLACE`, `MAP_STATE`.

`MASK_STRING` bắt buộc có `replacement` kiểu string. `REGEX_REPLACE` bắt buộc có `pattern` và `replacement` hợp lệ. Rule được áp dụng theo thứ tự trong file và chỉ khi endpoint khớp chính xác.

Ví dụ:

```json
{
  "rules": [
    {
      "endpoint": "POST /Users/AuthenticateByName",
      "path": "$.AccessToken",
      "action": "MASK_STRING",
      "replacement": "<SESSION_TOKEN>"
    }
  ]
}
```

## API và hành vi

API công khai:

```python
normalize(
    payload: Any,
    endpoint: str,
    state_mapping: Mapping[Any, Any] | None = None,
) -> Any
```

Không có endpoint mặc định. Cách này ngăn rule vô tình áp dụng toàn cục.

- `MASK_STRING`: thay mọi leaf kiểu `str` tại path bằng `replacement`; leaf kiểu khác giữ nguyên.
- `REGEX_REPLACE`: chỉ thay substring khớp regex trong leaf kiểu `str`; phần tĩnh của chuỗi được giữ nguyên.
- `MAP_STATE`: chỉ thay giá trị có khóa trong `state_mapping`; giá trị không map hoặc không hashable giữ nguyên.
- `DROP`: giữ hành vi hiện có.
- Input luôn được deep-copy và không bị mutate.

## Mutation fixtures và oracle

Fixtures nằm trong `tests/fixtures/normalization-cases.json`. Mỗi case có:

```json
{
  "name": "playback_noise_and_codec_bug",
  "endpoint": "GET /Items",
  "base": {},
  "mutated": {},
  "state_mapping": {},
  "expected_equal_after_normalization": false,
  "mutation_kind": "noise_and_real_bug"
}
```

Mọi case trước hết phải chứng minh `base != mutated`. Sau đó normalize hai phía bằng cùng endpoint và mapping:

- Noise-only phải hội tụ: kết quả bằng nhau.
- Bug-only phải phân kỳ: kết quả khác nhau.
- Noise + real bug phải phân kỳ.

Ma trận tối thiểu:

| Nhóm | Mutation | Kỳ vọng sau normalize |
| --- | --- | --- |
| `MASK_STRING` | Hai token string khác nhau | Bằng nhau |
| `MASK_STRING` | String so với `null`, number, object hoặc missing | Khác nhau |
| `REGEX_REPLACE` | Chỉ session ID trong URL khác | Bằng nhau |
| `REGEX_REPLACE` | Session ID và codec khác | Khác nhau |
| `REGEX_REPLACE` | URL khác nhưng không khớp regex | Khác nhau |
| `MAP_STATE` | Hai ID map về cùng canonical ID | Bằng nhau |
| `MAP_STATE` | ID không có mapping | Khác nhau |
| Wildcard | Noise trong nhiều phần tử | Bằng nhau |
| Wildcard | Một phần tử đổi field nghiệp vụ | Khác nhau |
| Endpoint scope | Cùng path nhưng endpoint khác | Khác nhau |
| Schema/collection | Thêm, xóa hoặc reorder dữ liệu nghiệp vụ | Khác nhau |

Fixtures bao phủ ba họ payload: authentication, playback và item collection.

## Xử lý lỗi

`SemanticNormalizer.from_file()` ném `NormalizerConfigError` cho root/rules không hợp lệ, endpoint thiếu hoặc sai định dạng, path/action không hợp lệ, thuộc tính action bị thiếu hoặc sai kiểu, regex/replacement không hợp lệ. Thông báo phải chứa index rule và path khi có để định vị cấu hình lỗi.

## Cấu trúc file

- `config/normalization-rules.json`: rules runtime có endpoint scope.
- `normalizer/semantic_normalizer.py`: compile endpoint và `MASK_STRING`; lọc rule khi normalize.
- `tests/test_semantic_normalizer.py`: unit tests contract, action và tương thích hành vi hiện có.
- `tests/fixtures/normalization-cases.json`: mutation cases xác định.
- `tests/test_normalization_mutations.py`: data-driven oracle trên production runtime rules.

## Tiêu chí hoàn thành

1. Runtime config nạp được; catalog G2-02 không bị sửa.
2. Noise-only hội tụ; bug-only và mixed mutation phân kỳ.
3. Missing, `null` và sai kiểu tại field noise vẫn bị phát hiện.
4. Endpoint mismatch không kích hoạt rule.
5. Wildcard, regex near-miss và unknown mapping được kiểm tra.
6. Input không bị mutate.
7. Toàn bộ test Normalizer và mutation suite pass offline bằng dependency hiện có.
