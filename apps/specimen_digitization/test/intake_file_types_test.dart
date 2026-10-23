import 'package:file_selector_ios/file_selector_ios.dart';
// The injected host API lets the real iOS plugin validate our filter first.
// ignore: implementation_imports
import 'package:file_selector_ios/src/messages.g.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/intake/intake_file_types.dart';

class RecordingFileSelectorApi extends FileSelectorApi {
  FileSelectorConfig? config;
  List<String> paths = [];

  @override
  Future<List<String>> openFile(FileSelectorConfig value) async {
    config = value;
    return paths;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'iOS accepts the photo filter for import, replacement and recovery',
    () async {
      final host = RecordingFileSelectorApi();
      final picker = FileSelectorIOS(api: host);
      host.paths = ['/private/photo.heic'];
      final selected = await picker.openFiles(
        acceptedTypeGroups: const [intakePhotoTypes],
      );
      expect(selected.single.path, '/private/photo.heic');
      expect(host.config!.utis, ['public.image']);
      expect(host.config!.allowMultiSelection, isTrue);

      final replacement = await picker.openFile(
        acceptedTypeGroups: const [intakePhotoTypes],
      );
      expect(replacement!.path, '/private/photo.heic');
      expect(host.config!.utis, ['public.image']);
      expect(host.config!.allowMultiSelection, isFalse);

      host.paths = [];
      expect(
        await picker.openFiles(acceptedTypeGroups: const [intakePhotoTypes]),
        isEmpty,
      );
      expect(
        await picker.openFile(acceptedTypeGroups: const [intakePhotoTypes]),
        isNull,
      );
    },
  );
}
