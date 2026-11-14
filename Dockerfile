FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git cmake g++ make curl && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.8.2 https://github.com/ggml-org/whisper.cpp /src && \
    test "$(git -C /src rev-parse HEAD)" = 4979e04f5dcaccb36057e059bbaed8a2f5288315 && \
    cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DWHISPER_BUILD_TESTS=OFF && \
    cmake --build /build --target whisper-cli -j2
RUN curl -fLsS --retry 3 https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin -o /tiny.bin && \
    echo '921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f  /tiny.bin' | sha256sum -c -

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends flite libstdc++6 && rm -rf /var/lib/apt/lists/* && \
    useradd --create-home agent && mkdir /data && chown agent /data
COPY --from=build /build/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=build /tiny.bin /models/tiny.bin
ENV WHISPER_MODEL=/models/tiny.bin
WORKDIR /app
COPY *.py ./
COPY static/ static/
COPY fixtures/ fixtures/
USER agent
EXPOSE 8765
CMD ["python","server.py","--bind","0.0.0.0","--db","/data/disputes.sqlite"]
