import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';

void main() {
  const id = '92c2aba8-c4e6-4f18-933b-51c62d45d7ea';

  test(
    'pilot filename supplies the short reference without changing identity',
    () {
      const specimen = Specimen({
        'specimen_id': id,
        'filename': 'subject_105526321.jpeg',
      });
      expect(specimen.displayReference, '#105526321');
      expect(specimen.id, id);
    },
  );

  test(
    'other filenames retain their full stem rather than guessing a number',
    () {
      const specimen = Specimen({
        'specimen_id': id,
        'filename': r'C:\photos\FMNH-INS-1007.JPG',
      });
      expect(specimen.displayReference, '#FMNH-INS-1007');
    },
  );

  test('asset filename and missing filename have explicit fallbacks', () {
    const specimen = Specimen({
      'specimen_id': id,
      'assets': [
        {'filename': '/images/subject_105526324.png'},
      ],
    });
    expect(specimen.displayReference, '#105526324');
    expect(const Specimen({'specimen_id': id}).displayReference, '#92c2aba8');
    expect(
      const Specimen({'specimen_id': 'fixture-001'}).displayReference,
      'fixture-001',
    );
  });

  test('identical filenames never replace distinct record identities', () {
    const first = Specimen({'specimen_id': 'one', 'filename': 'label.png'});
    const second = Specimen({'specimen_id': 'two', 'filename': 'label.png'});
    expect(first.displayReference, second.displayReference);
    expect(first.id, isNot(second.id));
  });
}
