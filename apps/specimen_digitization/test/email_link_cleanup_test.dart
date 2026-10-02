import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/email_link_cleanup.dart';

// Deliberately invented callback values; never capture a real sign-in URL here.
const origin = 'https://specimen-digitization.web.app';
const callback = '$origin/?mode=signIn&oobCode=test-code&apiKey=test-key';

void main() {
  test('completed callback is removed after the router changes its hash', () {
    expect(
      emailLinkCleanupLocation(
        Uri.parse(callback),
        Uri.parse('$callback#/setup'),
      ),
      '$origin/#/setup',
    );
  });

  test('cleanup retains an encoded record route and its fragment query', () {
    const route =
        '#/collections/org%2Finsects/queue/specimen%20one?tab=history';
    expect(
      emailLinkCleanupLocation(
        Uri.parse(callback),
        Uri.parse('$callback$route'),
      ),
      '$origin/$route',
    );
  });

  test('unchanged callback is removed without adding empty query or hash', () {
    final uri = Uri.parse(callback);
    expect(emailLinkCleanupLocation(uri, uri), '$origin/');
  });

  test('rejected callback queries are removable without decoding them', () {
    for (final query in [
      'mode=signIn',
      'mode=resetPassword&oobCode=test-code',
      'mode=signIn&oobCode=one&oobCode=two',
      'mode=signIn&oobCode=%FF&apiKey=test-key',
      'link=https%3A%2F%2Fexample.invalid%2Fcallback',
    ]) {
      final initial = Uri.parse('$origin/?$query');
      expect(emailLinkCleanupLocation(initial, initial), '$origin/');
      expect(
        emailLinkCleanupLocation(
          initial,
          Uri.parse('$origin/?$query#/sign-in'),
        ),
        '$origin/#/sign-in',
      );
    }
  });

  test('unchanged malformed callback fragment is cleared', () {
    final initial = Uri.parse('$origin/#oobCode=test-code');
    expect(emailLinkCleanupLocation(initial, initial), '$origin/');
    expect(
      emailLinkCleanupLocation(initial, Uri.parse('$origin/#/sign-in')),
      '$origin/#/sign-in',
    );
  });

  test('unchanged malformed callback query and fragment are both cleared', () {
    final initial = Uri.parse('$callback#oobCode=malformed-code');
    expect(emailLinkCleanupLocation(initial, initial), '$origin/');
  });

  test('a late acknowledgment cannot overwrite a newer callback or URL', () {
    final initial = Uri.parse(callback);
    for (final current in [
      '$origin/?mode=signIn&oobCode=newer-code&apiKey=test-key#/setup',
      '$callback&unrelated=keep#/setup',
      '$origin/help?mode=signIn&oobCode=test-code&apiKey=test-key#/setup',
      'https://example.invalid/?mode=signIn&oobCode=test-code&apiKey=test-key',
      'http://specimen-digitization.web.app/?mode=signIn&oobCode=test-code&apiKey=test-key',
      '$origin/#/setup',
      '$callback#oobCode=newer-fragment-code',
    ]) {
      expect(emailLinkCleanupLocation(initial, Uri.parse(current)), isNull);
    }
  });

  test('returning to an address without a fragment still removes callback', () {
    final initial = Uri.parse('$callback#oobCode=malformed-code');
    expect(emailLinkCleanupLocation(initial, Uri.parse(callback)), '$origin/');
  });
}
