import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Đổi 'latency_v10.8' -> 'latency_v10_8' (và v10.9)
const latency_v108 = new Trend('latency_v10_8');
const errorRate_v108 = new Rate('error_rate_v10_8');

const latency_v109 = new Trend('latency_v10_9');
const errorRate_v109 = new Rate('error_rate_v10_9');

export const options = {
    stages: [
        { duration: '30s', target: 10 },
        { duration: '30s', target: 50 },
        { duration: '30s', target: 100 },
        { duration: '10s', target: 0 },
    ],
    thresholds: {
        'latency_v10_8': ['p(95)<1000'],
        'latency_v10_9': ['p(95)<1000'],
        'error_rate_v10_8': ['rate<0.01'],
        'error_rate_v10_9': ['rate<0.01'],
    },
};

export default function () {
    const params = { headers: { 'Content-Type': 'application/json' } };

    // Dùng tên container nội bộ trong mạng docker_default
    const res_108 = http.get('http://jellyfin-v10.8.13-test:8096/System/Info/Public', params);
    latency_v108.add(res_108.timings.duration);
    errorRate_v108.add(res_108.status !== 200);

    const res_109 = http.get('http://jellyfin-v10.9.0-test:8096/System/Info/Public', params);
    latency_v109.add(res_109.timings.duration);
    errorRate_v109.add(res_109.status !== 200);

    sleep(0.1);
}