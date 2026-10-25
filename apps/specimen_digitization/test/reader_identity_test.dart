import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/reader_identity.dart';

void main() {
  test(
    'uses recorded model versions and preserves differing upstream identifiers',
    () {
      expect(
        readerModelName({'model_id': 'Qwen/Qwen3-VL-30B-A3B-Instruct'}),
        'Qwen/Qwen3-VL-30B-A3B-Instruct',
      );
      expect(
        readerModelName({
          'model_id': 'Muse-Glimmer-30B',
          'provider_model_id': 'generic-alias',
        }),
        'Muse-Glimmer-30B · generic-alias',
      );
      expect(
        readerModelName({'provider_model_id': 'family/model@2026-09-30'}),
        'family/model@2026-09-30',
      );
      expect(
        readerModelName({'route_id': 'unknown-reader'}),
        'Model not recorded',
      );
    },
  );

  test(
    'identity and model headings stay stable across observation order and labels',
    () {
      final a = <String, dynamic>{
        'model_id': 'model-a-v3',
        'route_id': 'reader-a',
        'region_id': 'label-1',
      };
      final b = <String, dynamic>{
        'model_id': 'model-b-v1',
        'route_id': 'reader-b',
      };
      final anotherLabel = <String, dynamic>{...a, 'region_id': 'label-2'};
      expect(
        readerNames([a, b, anotherLabel]),
        readerNames([b, anotherLabel, a]),
      );
      expect(readerNames([a, b, anotherLabel]).values, [
        'model-a-v3',
        'model-b-v1',
      ]);
      expect(readerIdentity(a), readerIdentity(anotherLabel));
      expect(
        readerIdentity({'provider_model_id': 'upstream/model-v2'}),
        isNotNull,
      );
      expect(readerIdentity({'provider': 'provider-only'}), isNull);
    },
  );

  test('provider and route distinguish duplicate models only when needed', () {
    Json reading(String provider, String route) => {
      'model_id': 'shared-model-v4',
      'provider': provider,
      'route_id': route,
    };
    final a = reading('first-provider', 'route-a');
    final b = reading('second-provider', 'route-b');
    final c = reading('second-provider', 'route-c');
    final names = readerNames([a, b, c]);
    expect(names[readerIdentity(a)], 'shared-model-v4 · first-provider');
    expect(
      names[readerIdentity(b)],
      'shared-model-v4 · second-provider · route-b',
    );
    expect(
      names[readerIdentity(c)],
      'shared-model-v4 · second-provider · route-c',
    );
    expect(readerNames([a])[readerIdentity(a)], 'shared-model-v4');
  });

  test('three readers keep their names and order whichever reads first', () {
    final qwen = <String, dynamic>{
      'model_id': 'Qwen/Qwen3-VL-30B-A3B-Instruct',
      'provider': 'novita',
    };
    final muse = <String, dynamic>{
      'model_id': 'meta-models/Muse-Glimmer-30B',
      'provider': 'deepinfra',
    };
    final third = <String, dynamic>{
      'model_id': 'nvidia/nemotron-nano-vl',
      'provider': 'nvidia',
    };
    final names = readerNames([qwen, muse, third]);
    expect(names.values.toSet(), {
      'Qwen/Qwen3-VL-30B-A3B-Instruct',
      'meta-models/Muse-Glimmer-30B',
      'nvidia/nemotron-nano-vl',
    });
    expect(readerNames([third, qwen, muse]), names);
    expect(readerNames([muse, third, qwen]), names);
    expect({
      readerIdentity(qwen),
      readerIdentity(muse),
      readerIdentity(third),
    }, hasLength(3));
  });

  test('a reader from a family with no verified mark gets none', () {
    expect(readerBrand({'model_id': 'nvidia/nemotron-nano-vl'}), isNull);
    expect(
      readerBrand({
        'model_id': 'alias',
        'provider_model_id': 'nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16',
        'provider': 'nvidia',
      }),
      isNull,
    );
  });

  test(
    'marks are matched to actual families, never their inference provider',
    () {
      expect(
        readerBrand({'model_id': 'Qwen/Qwen3-VL-30B-A3B-Instruct'}),
        ReaderBrand.qwen3Vl,
      );
      expect(
        readerBrand({
          'model_id': 'alias',
          'provider_model_id': 'meta-models/Muse-Glimmer-30B',
        }),
        ReaderBrand.muse,
      );
      expect(
        readerBrand({'model_id': 'qwen2.5-vl-72b', 'provider': 'novita'}),
        isNull,
      );
      expect(
        readerBrand({'model_id': 'unfamiliar-model', 'provider': 'deepinfra'}),
        isNull,
      );
      expect(readerBrand({'model_id': 'amusement-model'}), isNull);
      expect(readerBrand({'model_id': 'muse-video-model'}), isNull);
    },
  );
}
